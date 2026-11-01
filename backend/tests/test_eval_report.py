"""Eval metrics + report assembly + synthetic eval images. Pure logic; no model calls."""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import APIStatusError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.errors import UpstreamModelError  # noqa: E402
from app.domain.enums import Verdict  # noqa: E402
from app.domain.eval_images import (  # noqa: E402
    EVAL_IMAGE_PLAN,
    PHRASE_BOX,
    PHRASE_SACK,
    build_prompt,
    count_boxes,
    image_id,
    render_grid_html,
)
from app.domain.metrics import (  # noqa: E402
    count_summary,
    estimate_cost,
    latency_entries,
    macro_average,
    parse_cost_rates,
    verdict_score,
)
from app.domain.schemas.config import ModelConfig  # noqa: E402
from app.domain.schemas.dashboard import ModelCallStat  # noqa: E402
from app.domain.schemas.eval import (  # noqa: E402
    EvalImageLabel,
    EvalResults,
    ExpectedVerdict,
    ManifestLine,
    ModelUsage,
    ObservedLine,
    VerdictCaseResult,
)
from app.infra.meta.client import MetaModelClient  # noqa: E402
from app.infra.meta.sam import SamSegmenter  # noqa: E402
from app.services.eval_files import load_labels, save_labels  # noqa: E402
from app.services.eval_report import build_eval_results  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures" / "eval_report.json").read_text())


def _cases() -> list[VerdictCaseResult]:
    return [
        VerdictCaseResult(po_number=c["po_number"], expected=Verdict(c["expected"]),
                          predicted=Verdict(c["predicted"]), correct=c["expected"] == c["predicted"])
        for c in FIX["verdict_cases"]
    ]


# ------------------------------------------------------------------ metrics
def test_count_summary_all_measured() -> None:
    s = count_summary([tuple(p) for p in FIX["count_pairs"]["all_measured"]])
    assert (s.n, s.measured, s.correct) == (4, 4, 2)
    assert s.accuracy == 0.5
    assert s.mean_abs_error == (0 + 1 + 0 + 2) / 4


def test_count_summary_excludes_unmeasured_not_as_wrong() -> None:
    s = count_summary([tuple(p) for p in FIX["count_pairs"]["with_missing"]])
    assert (s.n, s.measured, s.correct) == (3, 2, 1)
    assert s.accuracy == 0.5


def test_count_summary_none_measured_is_null_not_zero() -> None:
    s = count_summary([tuple(p) for p in FIX["count_pairs"]["none_measured"]])
    assert s.measured == 0 and s.accuracy is None and s.mean_abs_error is None


def test_verdict_score_per_class_and_macro() -> None:
    score = verdict_score("served", _cases())
    assert score.cases_total == 6 and score.cases_correct == 4
    assert score.accuracy == pytest.approx(4 / 6)
    for m in score.per_class:
        exp = FIX["expected_class_metrics"][m.label.value]
        assert m.support == exp["support"]
        for key in ("precision", "recall"):
            if exp[key] is None:
                assert getattr(m, key) is None
            else:
                assert getattr(m, key) == pytest.approx(exp[key])
    # macro over the 3 labels with support: P=(1+2/3+1)/3, R=(.5+1+.5)/3
    assert score.macro_precision == pytest.approx((1 + 2 / 3 + 1) / 3)
    assert score.macro_recall == pytest.approx(2 / 3)
    f1s = [2 * 1 * 0.5 / 1.5, 2 * (2 / 3) / (5 / 3), 2 * 1 * 0.5 / 1.5]
    assert score.macro_f1 == pytest.approx(sum(f1s) / 3)
    # confusion: truth approve row predicted approve=1, partial_pay=1
    labels = [lb.value for lb in score.confusion.labels]
    assert score.confusion.matrix[labels.index("approve")][labels.index("partial_pay")] == 1
    assert score.confusion.matrix[labels.index("hold")][labels.index("human_review")] == 1


def test_macro_average_empty_is_none() -> None:
    assert verdict_score("agent", []).macro_f1 is None
    assert macro_average([]) == (None, None, None)


def test_latency_entries_live_calls_exclude_cache_hits() -> None:
    rows = latency_entries([ModelCallStat(**c) for c in FIX["model_calls"]])
    by = {(r.model, r.role): r for r in rows}
    a = by[("model-a", "decision")]
    assert (a.calls, a.live_calls, a.p50_ms, a.p95_ms) == (3, 2, 200.0, 290.0)


def test_cost_with_rates() -> None:
    rates = parse_cost_rates(FIX["rates_json"])
    usage = [ModelUsage(**u) for u in FIX["usage"]]
    c = estimate_cost(usage, rates, 4, "USD")
    assert c.rates_configured and c.currency == "USD"
    assert c.total_cost == pytest.approx(2 * 1.5 + 0.5 * 6.0 + 1 * 0.5)  # 6.5
    assert c.cost_per_delivery == pytest.approx(6.5 / 4)
    assert c.total_input_tokens == 3_000_000


def test_cost_without_rates_is_null_never_invented() -> None:
    usage = [ModelUsage(**u) for u in FIX["usage"]]
    c = estimate_cost(usage, parse_cost_rates(None), 4, None)
    assert not c.rates_configured
    assert c.total_cost is None and c.cost_per_delivery is None and c.currency is None
    assert all(m.cost is None for m in c.per_model)


def test_cost_partial_rates_gives_no_total() -> None:
    rates = parse_cost_rates(json.dumps({"model-a": {"input_per_1m": 1, "output_per_1m": 1}}))
    c = estimate_cost([ModelUsage(**u) for u in FIX["usage"]], rates, 2, "USD")
    assert c.total_cost is None and c.cost_per_delivery is None


def test_cost_no_deliveries_has_no_per_delivery() -> None:
    rates = parse_cost_rates(FIX["rates_json"])
    c = estimate_cost([ModelUsage(**u) for u in FIX["usage"]], rates, 0, "USD")
    assert c.total_cost == pytest.approx(6.5) and c.cost_per_delivery is None


def test_parse_cost_rates_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_cost_rates("not json")
    with pytest.raises(ValueError):
        parse_cost_rates("[1]")


# ------------------------------------------------------------ report assembly
def _manifest() -> list[ManifestLine]:
    return [
        ManifestLine(scenario="s1", category="cartons", true_count=12, true_damaged=0),
        ManifestLine(scenario="s4", category="bagged material", true_count=4, true_damaged=0),
    ]


def test_build_eval_results_partial_reports_not_measured() -> None:
    r = build_eval_results(
        manifest=_manifest(),
        observed=[ObservedLine(scenario="s1", category="cartons", observed_count=12, flagged_damaged=0,
                               source="eval_counts")],
        labels=[EvalImageLabel(id="img01", file="img01.png", prompt="p", phrase=PHRASE_BOX,
                               prompted_count=3, sam_count=3)],
        expected=[ExpectedVerdict(po_number="P1", verdict=Verdict.APPROVE)],
        served={}, served_unavailable_reason="no approved policy rules", agent={},
        calls=[], usage=[], deliveries_processed=0, rates={}, currency=None,
        now=datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert r.videos.count_summary.accuracy == 1.0 and r.videos.count_summary.n == 2
    assert r.videos.rows[1].source == "none" and r.videos.rows[1].count_correct is None
    assert r.images.images_total == 1 and r.images.images_confirmed == 0
    assert r.images.summary.accuracy is None and r.images.rows == []
    assert r.verdicts.served is None and r.verdicts.agent is None
    text = " | ".join(r.not_measured)
    for needle in ("video counts", "true_count confirmed", "served verdicts", "agent verdicts",
                   "latency", "cost", "cost per delivery"):
        assert needle in text
    EvalResults.model_validate_json(r.model_dump_json())  # round-trips


def test_build_eval_results_full() -> None:
    labels = [
        EvalImageLabel(id="img01", file="img01.png", prompt="p", phrase=PHRASE_BOX, prompted_count=5,
                       sam_count=5, true_count=5),
        EvalImageLabel(id="img02", file="img02.png", prompt="p", phrase=PHRASE_SACK, prompted_count=7,
                       sam_count=6, true_count=7),
    ]
    expected = [ExpectedVerdict(po_number="P1", verdict=Verdict.APPROVE),
                ExpectedVerdict(po_number="P2", verdict=Verdict.HOLD)]
    r = build_eval_results(
        manifest=_manifest(),
        observed=[ObservedLine(scenario="s1", category="cartons", observed_count=12, flagged_damaged=0, source="db"),
                  ObservedLine(scenario="s4", category="bagged_material", observed_count=5, flagged_damaged=0,
                               source="db")],
        labels=labels, expected=expected,
        served={"P1": Verdict.APPROVE, "P2": None}, served_unavailable_reason=None,
        agent={"P1": Verdict.APPROVE, "P2": Verdict.HOLD},
        calls=[ModelCallStat(model="m", purpose="x", latency_ms=10)],
        usage=[ModelUsage(model="m", input_tokens=1_000_000, output_tokens=0)],
        deliveries_processed=2,
        rates=parse_cost_rates('{"m": {"input_per_1m": 2, "output_per_1m": 4}}'), currency="USD",
    )
    assert r.videos.rows[1].observed_count == 5 and r.videos.rows[1].count_correct is False  # category normalised
    assert r.images.summary.accuracy == 0.5 and r.images.summary.mean_abs_error == 0.5
    assert r.verdicts.served is not None and r.verdicts.served.accuracy == 0.5  # None -> human_review
    assert r.verdicts.agent is not None and r.verdicts.agent.accuracy == 1.0 and r.verdicts.agent_reason is None
    assert r.cost.cost_per_delivery == 1.0
    assert r.not_measured == []


# --------------------------------------------------------------- eval images
def test_plan_spans_3_to_14_with_both_phrases() -> None:
    assert len(EVAL_IMAGE_PLAN) == 12
    assert sorted(c for c, _ in EVAL_IMAGE_PLAN) == list(range(3, 15))
    assert {p for _, p in EVAL_IMAGE_PLAN} == {PHRASE_BOX, PHRASE_SACK}
    assert image_id(1) == "img01" and image_id(12) == "img12"
    assert "top-down" in build_prompt(7, PHRASE_BOX).lower() and "exactly 7" in build_prompt(7, PHRASE_BOX)


def test_count_boxes_distinct_and_threshold() -> None:
    boxes = [("1", 0.9), ("2", 0.4), ("3", None), ("1", 0.95)]
    assert count_boxes(boxes, 0.5) == 2  # 1 (deduped) and 3 (no confidence)
    assert count_boxes([], 0.5) == 0


def test_labels_schema_roundtrip_and_defaults(tmp_path: Path) -> None:
    lb = EvalImageLabel(id="img01", file="img01.png", prompt="p", phrase=PHRASE_BOX, prompted_count=3)
    assert lb.true_count is None and lb.sam_count is None and lb.synthetic is True
    save_labels(tmp_path / "labels.json", [lb])
    raw = json.loads((tmp_path / "labels.json").read_text())
    assert raw[0]["true_count"] is None and raw[0]["synthetic"] is True
    assert load_labels(tmp_path / "labels.json") == [lb]
    assert load_labels(tmp_path / "missing.json") == []
    with pytest.raises(ValueError):
        EvalImageLabel(id="x", file="x.png", prompt="p", phrase="b", prompted_count=1, synthetic=False)  # type: ignore[arg-type]


def test_grid_html_lists_every_image_and_marks_synthetic() -> None:
    labels = [EvalImageLabel(id=image_id(i + 1), file=f"{image_id(i + 1)}.png", prompt="p", phrase=ph,
                             prompted_count=c, sam_count=c if i % 2 else None)
              for i, (c, ph) in enumerate(EVAL_IMAGE_PLAN)]
    page = render_grid_html(labels)
    assert page.count("<figure>") == 12 and "SYNTHETIC" in page and "img12.png" in page
    assert "confirm_eval_images.py" in page and "—" in page  # unknown sam_count shown as a dash


# ------------------------------------------------- clients with a fake backend
CFG = ModelConfig(model_api_key="k", meta_base_url="http://x", perception_model="pm", decision_model="dm",
                  compiler_model="cm", bulk_model="bm", seg_model="seg", image_model="img", voice_model="vm")

_MASK = "!!!!!&T:u9`"


def _sam_text() -> str:
    box = "<|box;x1={x};y1=20;x2={x2};y2=120;w=1000;h=800;c={c}|><|mask;x=0;y=0;data=2,2," + _MASK + "|>"
    return "<0f>1" + box.format(x=10, x2=110, c=0.95) + ",2" + box.format(x=200, x2=300, c=0.3)


class _Event:
    def __init__(self, data: dict[str, Any]) -> None:
        self._d = data

    def model_dump(self) -> dict[str, Any]:
        return self._d


class _Stream:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    async def __aenter__(self) -> _Stream:
        return self

    async def __aexit__(self, *a: object) -> None:
        return None

    def __aiter__(self) -> _Stream:
        self._it = iter(self._events)
        return self

    async def __anext__(self) -> _Event:
        try:
            return _Event(next(self._it))
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Stream:
        self.calls.append(kwargs)
        text = _sam_text()
        base = {"item_id": "i", "output_index": 0, "content_index": 0}
        return _Stream([
            {"type": "response.output_text.delta", "delta": text, **base},
            {"type": "response.content_part.done", "part": {"type": "output_text", "text": text}, **base},
            {"type": "response.completed", "response": {"usage": {"input_tokens": 5, "output_tokens": 2}}},
        ])


class _FakeAPI:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def test_segment_image_parses_caches_and_never_recalls(tmp_path: Path) -> None:
    api = _FakeAPI()
    seg = SamSegmenter(CFG, tmp_path, client=api)  # type: ignore[arg-type]
    first = asyncio.run(seg.segment_image(image_bytes=b"imgbytes", mime="image/png", phrase=PHRASE_BOX))
    assert not first.cache_hit and len(first.boxes) == 2
    assert count_boxes([(b.object_id, b.confidence) for b in first.boxes], 0.5) == 1
    sent = api.responses.calls[0]
    content = sent["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": PHRASE_BOX}
    assert content[1]["type"] == "input_image" and content[1]["image_url"].startswith("data:image/png;base64,")
    assert sent["model"] == "seg" and sent["stream"] is True
    second = asyncio.run(SamSegmenter(CFG, tmp_path, client=api).segment_image(  # type: ignore[arg-type]
        image_bytes=b"imgbytes", mime="image/png", phrase=PHRASE_BOX))
    assert second.cache_hit and len(api.responses.calls) == 1 and second.boxes == first.boxes
    other = asyncio.run(seg.segment_image(image_bytes=b"imgbytes", mime="image/png", phrase=PHRASE_SACK))
    assert not other.cache_hit and len(api.responses.calls) == 2  # phrase is part of the key


class _Images:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def generate(self, **kwargs: Any) -> Any:
        self.calls += 1
        assert kwargs["model"] == "img" and kwargs["n"] == 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class _Api:
    def __init__(self, images: _Images) -> None:
        self.images = images


def _status_error(code: int) -> APIStatusError:
    req = httpx.Request("POST", "http://x/v1/images/generations")
    return APIStatusError("boom", response=httpx.Response(code, request=req), body=None)


class _Resp:
    def __init__(self, raw: bytes) -> None:
        self.data = [type("Item", (), {"b64_json": base64.b64encode(raw).decode(), "url": None})()]
        self.usage = None


def test_generate_image_retries_5xx_then_returns_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr("app.infra.meta.client.asyncio.sleep", _no_sleep)
    images = _Images([_status_error(503), _Resp(b"RIFFwebp")])
    client = MetaModelClient(CFG, client=_Api(images))  # type: ignore[arg-type]
    out = asyncio.run(client.generate_image(purpose="eval_image_generation", model="img", prompt="p"))
    assert out == b"RIFFwebp" and images.calls == 2


def test_generate_image_does_not_retry_4xx() -> None:
    images = _Images([_status_error(400), _Resp(b"x")])
    client = MetaModelClient(CFG, client=_Api(images))  # type: ignore[arg-type]
    with pytest.raises(UpstreamModelError):
        asyncio.run(client.generate_image(purpose="eval_image_generation", model="img", prompt="p"))
    assert images.calls == 1


def test_generate_image_rejects_model_not_from_config() -> None:
    client = MetaModelClient(CFG, client=_Api(_Images([])))  # type: ignore[arg-type]
    with pytest.raises(Exception, match="did not come from ModelConfig"):
        asyncio.run(client.generate_image(purpose="p", model="made-up", prompt="p"))


# ------------------------------------------- DB-backed collection (seeded tmp DB)
def test_collect_eval_results_from_seeded_db(tmp_path: Path) -> None:
    from app.infra.db.models import Decision, Delivery, ModelCall, PerceptionResult, PurchaseOrder, Rule, SamRun
    from app.infra.db.repositories.cases import SqlCaseRepository
    from app.infra.db.repositories.evaluation import SqlEvaluationRepository
    from app.infra.db.session import make_engine, make_session_factory
    from app.seed.generate import seed
    from app.services.cases import CaseService
    from app.services.eval_files import load_eval_counts, load_expected_verdicts, load_manifest
    from app.services.eval_report import collect_eval_results

    db = tmp_path / "e.db"
    seed(db_path=db, manifest_path=ROOT / "samples" / "scenarios" / "manifest.json",
         policy_path=ROOT / "data" / "policy" / "receiving_policy.md", truth_path=tmp_path / "gt.json")
    factory = make_session_factory(make_engine(db))
    manifest = load_manifest(ROOT / "samples" / "scenarios" / "manifest.json")
    expected = load_expected_verdicts(ROOT / "data" / "ground_truth.json")
    exported = load_eval_counts(ROOT / "data" / "eval_counts.json")
    assert len(manifest) == 5 and len(expected) == 12 and len(exported) == 5

    with factory() as s:
        repo = SqlEvaluationRepository(s)
        served = {c.po_number: c.verdict for c in CaseService(SqlCaseRepository(s)).list_cases()}
        empty = collect_eval_results(repo, manifest=manifest, exported_counts=exported, labels=[],
                                     expected=expected, served=served, rates={}, currency=None)
        assert empty.videos.count_summary.accuracy == 1.0 and {r.source for r in empty.videos.rows} == {"eval_counts"}
        assert empty.verdicts.served is None and "no approved policy rules" in (empty.verdicts.served_reason or "")
        assert empty.verdicts.agent is None and empty.latency == [] and empty.cost.deliveries_processed == 0

        # a stored DB perception row beats the exported file and is scored against the MANIFEST truth
        delivery = s.query(Delivery).filter_by(scenario_id="scn1_clean").one()
        run = SamRun(delivery_id=delivery.id, video_sha256="0" * 64, seg_model="cfg-seg", prompt="p",
                     category="cartons", status="completed")
        s.add(run)
        s.flush()
        po = s.get(PurchaseOrder, delivery.po_id)
        assert po is not None
        s.add(PerceptionResult(delivery_id=delivery.id, po_line_id=po.lines[0].id, sam_run_id=run.id,
                               category="cartons", noun_phrase="cardboard box", observed_count=11, max_visible=11,
                               damaged_track_ids=[], evidence_quality="reliable", reasons=[]))
        s.add(Decision(po_id=po.id, delivery_id=delivery.id, verdict="approve", reason="r", source="agent"))
        s.add(Decision(po_id=po.id + 1, delivery_id=None, verdict="hold", reason="r", source="fallback"))
        s.add(ModelCall(purpose="decision", model="cfg-d", latency_ms=200, input_tokens=1000, output_tokens=100,
                        status="ok"))
        s.add(ModelCall(purpose="decision", model="cfg-d", latency_ms=0, input_tokens=None, status="ok",
                        cache_hit=True))
        s.add(Rule(clause="4.2", policy_version="1.0", rule_type="compiled:x", action="hold", description="d",
                   rule_id="R-x", status="approved"))
        s.commit()

        res = collect_eval_results(
            repo, manifest=manifest, exported_counts=exported, labels=[], expected=expected, served=served,
            rates=parse_cost_rates('{"cfg-d": {"input_per_1m": 1000, "output_per_1m": 2000}}'), currency="INR")
        row = next(r for r in res.videos.rows if r.scenario == "scn1_clean")
        assert row.source == "db" and row.observed_count == 11 and row.count_correct is False
        assert res.videos.count_summary.correct == 4
        assert res.verdicts.served is not None and res.verdicts.served.cases_total == 12
        assert res.verdicts.agent is not None and res.verdicts.agent.cases_total == 1  # fallback row excluded
        assert "1 of 12" in (res.verdicts.agent_reason or "")
        assert res.cost.deliveries_processed == 1 and res.cost.total_cost == pytest.approx(1.0 + 0.2)
        assert res.cost.cost_per_delivery == pytest.approx(1.2)
        assert [(r.calls, r.live_calls) for r in res.latency] == [(2, 1)]
        EvalResults.model_validate_json(res.model_dump_json())


def test_dashboard_eval_includes_results_file_and_falls_back_to_its_latency(tmp_path: Path) -> None:
    from app.infra.db.repositories.cases import SqlCaseRepository
    from app.infra.db.repositories.dashboard import SqlDashboardRepository
    from app.infra.db.session import make_engine, make_session_factory
    from app.seed.generate import seed
    from app.services.cases import CaseService
    from app.services.dashboard import DashboardService, DataFilesError
    from app.services.eval_files import save_results

    db = tmp_path / "d.db"
    seed(db_path=db, manifest_path=ROOT / "samples" / "scenarios" / "manifest.json",
         policy_path=ROOT / "data" / "policy" / "receiving_policy.md", truth_path=tmp_path / "gt.json")
    results = build_eval_results(
        manifest=_manifest(), observed=[], labels=[], expected=[], served={}, served_unavailable_reason="x",
        agent={}, calls=[ModelCallStat(model="m", purpose="x", latency_ms=40)], usage=[],
        deliveries_processed=0, rates={}, currency=None)
    path = tmp_path / "eval_results.json"
    save_results(path, results)

    def service(s: Any, results_path: Path | None) -> DashboardService:
        return DashboardService(
            CaseService(SqlCaseRepository(s)), SqlDashboardRepository(s),
            ground_truth_path=ROOT / "data" / "ground_truth.json",
            eval_counts_path=ROOT / "data" / "eval_counts.json", eval_results_path=results_path)

    with make_session_factory(make_engine(db))() as s:
        read = service(s, path).evaluation()
        assert read.results is not None and read.results.images.synthetic is True
        assert [(r.model, r.p50_ms) for r in read.latency] == [("m", 40.0)]  # DB has no calls -> file latency
        assert service(s, None).evaluation().results is None
        assert service(s, tmp_path / "absent.json").evaluation().results is None
        bad = tmp_path / "bad.json"
        bad.write_text('{"schema_version": 1}')
        with pytest.raises(DataFilesError):
            service(s, bad).evaluation()
