"""Decision agent: loop, guards, fallback, persistence, events, API shapes.
No network and no model calls -- a scripted FakeModelClient replays tool calls."""
from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from fakes import FakeModelClient, Step, upstream_error  # noqa: E402

from app.api.deps import get_db_session, get_decision_agent, get_delivery_service  # noqa: E402
from app.domain import agent_logic  # noqa: E402
from app.domain.schemas.config import ModelConfig  # noqa: E402
from app.domain.schemas.decision_agent import RecordDecisionPayload  # noqa: E402
from app.infra.db.models import (  # noqa: E402
    Decision,
    Delivery,
    Grn,
    GrnLine,
    Invoice,
    InvoiceLine,
    Job,
    JobEvent,
    ModelCall,
    PerceptionResult,
    PoLine,
    PurchaseOrder,
    Rule,
    SamRun,
    Track,
    Vendor,
)
from app.infra.db.repositories.cases import SqlCaseRepository  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.infra.meta.client import MetaModelClient  # noqa: E402
from app.infra.storage import LocalFileStore  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.case_facts import build_case_facts  # noqa: E402
from app.services.decision_agent import DecisionAgent  # noqa: E402
from app.services.deliveries import DeliveryService  # noqa: E402
from app.services.perception import PerceptionPipeline  # noqa: E402

RULE_ID = "R-4.2-cartons"
VIDEO_BYTES = b"0123456789" * 100


@dataclass
class World:
    factory: sessionmaker[Session]
    po_id: int
    delivery_id: int
    line_id: int
    invoice_id: int
    video: Path
    storage: Path
    observed: int


def make_world(tmp_path: Path, *, quality: str = "reliable", observed: int = 9) -> World:
    engine = make_engine(tmp_path / "agent.db")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    s = factory()
    vendor = Vendor(code="TST", name="Test Vendor Ltd", gstin="27FAKEX1234F1Z5", city="Pune", state="MH",
                    primary_category="cartons", contact_name="A", contact_email="a@example.com")
    s.add(vendor)
    s.flush()
    po = PurchaseOrder(po_number="FM/PO/26-27/901", vendor_id=vendor.id, order_date=date(2026, 10, 1),
                       expected_date=date(2026, 10, 8), status="received", total_paise=12 * 55000,
                       synthetic=True)
    s.add(po)
    s.flush()
    line = PoLine(po_id=po.id, line_no=1, category="cartons", sku="CTN-550", description="Cartons",
                  unit="box", qty_ordered=12, unit_price_paise=55000, tolerance_pct=0.0,
                  line_total_paise=12 * 55000)
    s.add(line)
    s.flush()
    grn = Grn(grn_number="GRN-901", po_id=po.id, received_date=date(2026, 10, 5),
              storekeeper_name="Stores", signed=True, synthetic=True)
    s.add(grn)
    s.flush()
    s.add(GrnLine(grn_id=grn.id, po_line_id=line.id, qty_received=12, qty_damaged=0))
    inv = Invoice(invoice_number="INV-901", po_id=po.id, vendor_id=vendor.id, invoice_date=date(2026, 10, 6),
                  due_date=date(2026, 11, 5), total_paise=12 * 55000, synthetic=True)
    s.add(inv)
    s.flush()
    s.add(InvoiceLine(invoice_id=inv.id, po_line_id=line.id, qty_invoiced=12, unit_price_paise=55000,
                      line_total_paise=12 * 55000))
    video = tmp_path / "dock.mp4"
    video.write_bytes(VIDEO_BYTES)
    delivery = Delivery(po_id=po.id, status="recorded", video_path=str(video))
    s.add(delivery)
    s.flush()
    run = SamRun(delivery_id=delivery.id, video_sha256="b" * 64, seg_model="seg-test", prompt="carton",
                 category="cartons", status="completed")
    s.add(run)
    s.flush()
    for n in range(1, observed + 1):
        s.add(Track(delivery_id=delivery.id, sam_run_id=run.id, object_id=str(n), prompt="carton",
                    category="cartons", first_frame=0, last_frame=20, frame_count=20))
    s.add(PerceptionResult(delivery_id=delivery.id, po_line_id=line.id, sam_run_id=run.id,
                           category="cartons", noun_phrase="carton", observed_count=observed,
                           max_visible=observed, per_frame_counts=[observed], damaged_track_ids=[],
                           evidence_quality=quality, reasons=[]))
    s.add(Rule(clause="4.2", policy_version="1.0", category="cartons", rule_type="quantity_variance",
               action="partial_pay", description="Quantity variance.", rule_id=RULE_ID,
               goods_category="cartons", condition_field="variance_pct", condition_op=">",
               condition_value=0.0, source_text="Quantity variance beyond tolerance holds the disputed portion.",
               status="approved", validation_errors=[], conflict_with=[]))
    s.commit()
    world = World(factory, po.id, delivery.id, line.id, inv.id, video, tmp_path / "storage", observed)
    s.close()
    return world


def good_payload(w: World, **over: Any) -> dict[str, Any]:
    variance = round((12 - w.observed) / 12 * 100, 2)
    payload: dict[str, Any] = {
        "verdict": "partial_pay",
        "amount_held_paise": (12 - w.observed) * 55000,
        "lines": [{"po_line_id": w.line_id, "po": 12, "grn": 12, "invoiced": 12, "observed": w.observed,
                   "variance_pct": variance, "rule_id": RULE_ID, "clause": "4.2",
                   "evidence": ["track:1", "frame:5"]}],
        "summary_en": "Pay the received portion. Rs 1,650 is held for 3 missing cartons.",
        "recommended_action": "Raise a debit note.",
    }
    payload.update(over)
    return payload


def research(w: World) -> list[Step]:
    return [("compute_variance", {"po_line_id": w.line_id}),
            ("get_rules", {"goods_category": "cartons"}),
            ("evaluate_rule", {"rule_id": RULE_ID, "po_line_id": w.line_id})]


def agent_for(w: World, script: list[list[Step] | Exception]) -> tuple[DecisionAgent, FakeModelClient]:
    fake = FakeModelClient(script)
    return DecisionAgent(w.factory, fake, "test-decision-model", max_turns=10), fake  # type: ignore[arg-type]


def happy_script(w: World, payload: dict[str, Any] | None = None) -> list[list[Step] | Exception]:
    return [[("get_case", {"delivery_id": w.delivery_id})], research(w),
            [("record_decision", payload or good_payload(w))]]


@pytest.fixture()
def world(tmp_path: Path) -> World:
    return make_world(tmp_path)


def run(agent: DecisionAgent, w: World) -> Any:
    return asyncio.run(agent.run_standalone(w.delivery_id))


def events(w: World) -> list[str]:
    s = w.factory()
    try:
        return [e.event_type for e in s.query(JobEvent).order_by(JobEvent.id).all()]
    finally:
        s.close()


# ----------------------------------------------------------------- the loop
def test_happy_path_partial_pay(world: World) -> None:
    agent, fake = agent_for(world, happy_script(world))
    read = run(agent, world)
    assert read.verdict.value == "partial_pay"
    assert read.amount_held_paise == 165000  # (12 invoiced - 9 payable) * 55000
    assert read.source == "agent" and read.fallback_reasons == []
    assert read.model == "test-decision-model"
    # Spec: effort high, tools offered, decision model from config argument, verbatim prompt.
    req = fake.requests[0]
    assert req["effort"] == "high" and req["model"] == "test-decision-model"
    assert req["instructions"].startswith("You are FourthMatch's payment-decision agent.")
    assert "amount_held_paise (integer paise)" in req["instructions"]
    assert {t["name"] for t in req["tools"]} == {
        "get_case", "compute_variance", "get_rules", "evaluate_rule", "draft_debit_note", "record_decision"}


def test_trace_persisted_in_order(world: World) -> None:
    agent, _ = agent_for(world, happy_script(world))
    run(agent, world)
    s = world.factory()
    row = s.query(Decision).one()
    assert [(st["seq"], st["tool"]) for st in row.trace] == [
        (1, "get_case"), (2, "compute_variance"), (3, "get_rules"), (4, "evaluate_rule"),
        (5, "record_decision")]
    assert row.trace[1]["args"] == {"po_line_id": world.line_id}
    assert row.trace[1]["result"]["variance_pct"] == 25.0
    assert row.trace[1]["result"]["value_at_risk_paise"] == 165000
    assert all(isinstance(st["latency_ms"], int) for st in row.trace)
    assert row.verdict == "partial_pay" and row.amount_held_paise == 165000
    assert row.source == "agent" and row.model == "test-decision-model"
    assert row.policy_clauses == ["4.2"] and row.job_id
    s.close()


def test_events_reconciling_policy_verdict(world: World) -> None:
    agent, _ = agent_for(world, happy_script(world))
    run(agent, world)
    seen = events(world)
    order = [seen.index(k) for k in ("reconciling", "applying_policy", "verdict", "done")]
    assert order == sorted(order)
    s = world.factory()
    verdict_event = s.query(JobEvent).filter(JobEvent.event_type == "verdict").one()
    assert verdict_event.payload == {"verdict": "partial_pay", "held_paise": 165000}
    assert s.query(Job).one().status == "done"
    s.close()


def test_skipping_compute_variance_rejected_then_retried(world: World) -> None:
    script: list[list[Step] | Exception] = [
        [("get_case", {"delivery_id": world.delivery_id})],
        [("get_rules", {"goods_category": "cartons"}),
         ("evaluate_rule", {"rule_id": RULE_ID, "po_line_id": world.line_id})],
        [("record_decision", good_payload(world))],            # rejected: no compute_variance
        [("compute_variance", {"po_line_id": world.line_id})],
        [("record_decision", good_payload(world))],            # accepted
    ]
    agent, fake = agent_for(world, script)
    read = run(agent, world)
    assert read.source == "agent"
    records = [s for s in read.trace if s.tool == "record_decision"]
    assert [r.result["accepted"] for r in records] == [False, True]
    assert "compute_variance was not called" in records[0].result["errors"][0]
    # The rejection was fed back to the model as a function_call_output.
    last_input = fake.requests[-1]["input_items"]
    assert any(i.get("type") == "function_call_output" and "compute_variance was not called" in i["output"]
               for i in last_input)


def test_wrong_amount_rejected_then_corrected(world: World) -> None:
    script = happy_script(world, good_payload(world, amount_held_paise=999)) + [
        [("record_decision", good_payload(world))]]
    agent, _ = agent_for(world, script)
    read = run(agent, world)
    records = [s for s in read.trace if s.tool == "record_decision"]
    assert records[0].result["accepted"] is False
    assert "amount_held_paise 999 is wrong" in records[0].result["errors"][0]
    assert read.source == "agent" and read.amount_held_paise == 165000


def test_unknown_ids_rejected_by_guard(world: World) -> None:
    s = world.factory()
    facts = build_case_facts(SqlCaseRepository(s), world.delivery_id)
    s.close()
    from app.domain.schemas.decision_agent import ToolCoverage
    cover = ToolCoverage(variance_lines={world.line_id}, evaluated={(RULE_ID, world.line_id)})

    def check(**line_over: Any) -> list[str]:
        payload = good_payload(world)
        payload["lines"][0].update(line_over)
        return agent_logic.validate_payload(RecordDecisionPayload.model_validate(payload), facts, cover).errors

    assert check() == []
    assert any("unknown rule_id" in e for e in check(rule_id="R-NOPE"))
    assert any("unknown track_id '999'" in e for e in check(evidence=["track:999", "frame:5"]))
    assert any("unknown frame_index 999" in e for e in check(evidence=["track:1", "frame:999"]))
    assert any("unknown po_line_id 4242" in e for e in check(po_line_id=4242))
    assert any("video line must cite" in e for e in check(evidence=[]))
    assert any("clause must be" in e for e in check(clause="9.9"))
    assert any("observed is 3" in e for e in check(observed=3))


def test_insufficient_evidence_forces_human_review(tmp_path: Path) -> None:
    w = make_world(tmp_path, quality="insufficient", observed=4)
    payload = good_payload(w, verdict="approve", amount_held_paise=12 * 55000)
    agent, _ = agent_for(w, happy_script(w, payload))
    read = run(agent, w)
    assert read.verdict.value == "human_review"      # never approve
    assert read.amount_held_paise == 660000          # full line value held, Python recompute
    assert read.source == "agent"
    s = w.factory()
    assert s.query(Decision).one().verdict == "human_review"
    s.close()


def test_fallback_after_two_invalid_attempts(world: World) -> None:
    bad = good_payload(world, amount_held_paise=1)
    script = happy_script(world, bad) + [[("record_decision", bad)]]
    agent, _ = agent_for(world, script)
    read = run(agent, world)
    assert read.source == "fallback"
    assert read.verdict.value == "partial_pay" and read.amount_held_paise == 165000
    assert len(read.fallback_reasons) == 2 and "attempt 1 rejected" in read.fallback_reasons[0]
    assert "Rs" not in read.summary_en and "₹1,650" in read.summary_en
    s = world.factory()
    row = s.query(Decision).one()
    assert row.source == "fallback" and row.decided_by == "fallback"
    assert len(row.fallback_reasons) == 2
    s.close()


def test_fallback_on_model_error_and_turn_cap(world: World) -> None:
    agent, _ = agent_for(world, [upstream_error()])
    read = run(agent, world)
    assert read.source == "fallback" and read.fallback_reasons == ["model_error:model_upstream"]

    agent2, _ = agent_for(world, [[("get_case", {"delivery_id": world.delivery_id})]] * 10)
    read2 = run(agent2, world)
    assert read2.source == "fallback" and read2.fallback_reasons[-1] == "max_turns_exceeded"


def test_fallback_payload_passes_the_guards(world: World) -> None:
    s = world.factory()
    facts = build_case_facts(SqlCaseRepository(s), world.delivery_id)
    s.close()
    from app.domain.schemas.decision_agent import ToolCoverage
    cover = ToolCoverage(variance_lines={world.line_id}, evaluated=agent_logic.applicable_pairs(facts))
    assert agent_logic.validate_payload(agent_logic.fallback_payload(facts), facts, cover).errors == []


def test_debit_note_tool_is_python_money(world: World) -> None:
    script: list[list[Step] | Exception] = [
        [("draft_debit_note", {"invoice_id": world.invoice_id,
                               "lines": [{"po_line_id": world.line_id, "reason": "short"}]}),
         ("draft_debit_note", {"invoice_id": 999, "lines": []})]] + happy_script(world)[1:]
    agent, _ = agent_for(world, script)
    read = run(agent, world)
    ok, bad = read.trace[0].result, read.trace[1].result
    assert ok["total_paise"] == 165000 and ok["lines"][0]["qty"] == 3
    assert "unknown invoice_id" in bad["error"]


# ------------------------------------------------------------ client + API
def test_call_tool_turn_shapes_and_model_call_row(world: World) -> None:
    sent: list[dict[str, Any]] = []

    class Item:
        def __init__(self, data: dict[str, Any]) -> None:
            self._d = data
            self.type, self.name = data["type"], data.get("name")
            self.arguments, self.call_id = data.get("arguments"), data.get("call_id")

        def model_dump(self) -> dict[str, Any]:
            return self._d

    async def create(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return SimpleNamespace(
            output=[Item({"type": "reasoning", "encrypted_content": "x"}),
                    Item({"type": "function_call", "name": "get_case", "arguments": "{}", "call_id": "c1"})],
            output_text="", usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18))

    cfg = ModelConfig(model_api_key="k", meta_base_url="http://x", perception_model="m-p", decision_model="m-d",
                      compiler_model="m-c", bulk_model="m-b", seg_model="m-s", image_model="m-i", voice_model="m-v")
    stub = SimpleNamespace(responses=SimpleNamespace(create=create))
    client = MetaModelClient(cfg, client=stub)  # type: ignore[arg-type]
    s = world.factory()
    turn = asyncio.run(client.call_tool_turn(
        purpose="decision_agent", model="m-d", instructions="sys", input_items=[{"type": "message"}],
        tools=[{"type": "function", "name": "get_case"}], session=s, reasoning_effort="high"))
    assert sent[0]["include"] == ["reasoning.encrypted_content"]
    assert "previous_response_id" not in sent[0]
    assert sent[0]["reasoning"] == {"effort": "high"} and sent[0]["model"] == "m-d"
    assert turn.calls[0].name == "get_case" and turn.output_items[0]["type"] == "reasoning"
    row = s.query(ModelCall).one()
    assert (row.purpose, row.model, row.input_tokens, row.output_tokens, row.status) == (
        "decision_agent", "m-d", 11, 7, "ok")
    assert row.latency_ms is not None
    s.close()


@pytest.fixture()
def api(world: World) -> Iterator[tuple[TestClient, World, FakeModelClient | None]]:
    def override_session() -> Iterator[Session]:
        s = world.factory()
        try:
            yield s
        finally:
            s.close()

    holder: dict[str, DecisionAgent] = {}
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_delivery_service] = lambda: DeliveryService(
        world.factory, LocalFileStore(world.storage))
    app.dependency_overrides[get_decision_agent] = lambda: holder["agent"]
    with TestClient(app) as client:
        client.holder = holder  # type: ignore[attr-defined]
        yield client, world, None


def test_decide_endpoint_smoke_and_case_shapes(api: tuple[TestClient, World, None]) -> None:
    client, w, _ = api
    client.holder["agent"] = agent_for(w, happy_script(w))[0]  # type: ignore[attr-defined]
    resp = client.post(f"/api/deliveries/{w.delivery_id}/decide")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"verdict", "amount_held_paise", "summary_en", "recommended_action", "model", "trace"}
    assert body["verdict"] == "partial_pay" and body["amount_held_paise"] == 165000
    assert set(body["trace"][0]) == {"seq", "tool", "args", "result", "latency_ms"}

    case = client.get(f"/api/cases/{w.po_id}").json()
    assert case["decision"]["verdict"] == "partial_pay"
    assert case["decision"]["amount_held_paise"] == 165000
    assert case["decision"]["stale"] is False and case["decision"]["source"] == "agent"
    assert len(case["decision"]["trace"]) == 5
    assert case["video_url"] == f"/api/deliveries/{w.delivery_id}/video"
    assert case["invoice_total_paise"] == 660000
    assert case["evidence_source"] == "video" and case["decided_at"]
    assert case["clauses"] == ["4.2"]
    assert case["discrepancy_types"] == ["grn_contradicted_by_video", "short_shipment_beyond_tolerance"]
    (line,) = case["lines"]
    assert line["perception"] == {
        "noun_phrase": "carton", "observed_count": 9, "max_visible": 9,
        "track_ids": [str(n) for n in range(1, 10)], "damaged_track_ids": [], "reasons": [],
        "footage_needed": None}
    # Summary list carries the new optional fields too.
    (summary,) = [c for c in client.get("/api/cases").json() if c["po_id"] == w.po_id]
    assert summary["discrepancy_types"] == case["discrepancy_types"] and summary["clauses"] == ["4.2"]
    assert summary["evidence_source"] == "video" and summary["decided_at"] == case["decided_at"]

    # Served verdict stays the Python recompute; the stored decision is marked stale
    # when the policy changes underneath it.
    s = w.factory()
    s.query(Rule).update({"status": "pending_approval"})
    s.commit()
    s.close()
    stale = client.get(f"/api/cases/{w.po_id}").json()
    assert stale["verdict"] == "approve" and stale["decision"]["stale"] is True
    assert stale["decision"]["verdict"] == "partial_pay"


def test_case_without_decision_has_null_decision(api: tuple[TestClient, World, None]) -> None:
    client, w, _ = api
    case = client.get(f"/api/cases/{w.po_id}").json()
    assert case["decision"] is None and case["decided_at"] is None


def test_video_endpoint_smoke_and_range(api: tuple[TestClient, World, None]) -> None:
    client, w, _ = api
    resp = client.get(f"/api/deliveries/{w.delivery_id}/video")
    assert resp.status_code == 200 and resp.headers["content-type"] == "video/mp4"
    assert resp.content == VIDEO_BYTES
    part = client.get(f"/api/deliveries/{w.delivery_id}/video", headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == VIDEO_BYTES[:10]
    missing = client.get("/api/deliveries/4242/video")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "delivery_not_found"


def test_decide_unknown_delivery_404(api: tuple[TestClient, World, None]) -> None:
    client, w, _ = api
    client.holder["agent"] = agent_for(w, [])[0]  # type: ignore[attr-defined]
    resp = client.post("/api/deliveries/4242/decide")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "delivery_not_found"


def test_pipeline_hook_appends_events_to_the_perception_job(world: World) -> None:
    s = world.factory()
    job = Job(kind="perception", status="damage_check", delivery_id=world.delivery_id, po_id=world.po_id)
    s.add(job)
    s.commit()
    job_id = job.id
    s.close()
    agent, _ = agent_for(world, happy_script(world))
    pipeline = object.__new__(PerceptionPipeline)
    pipeline._decision_agent = agent  # type: ignore[attr-defined]
    pipeline._factory = world.factory  # type: ignore[attr-defined]
    asyncio.run(pipeline._run_decision(job_id, world.delivery_id))  # type: ignore[attr-defined]
    s = world.factory()
    kinds = [e.event_type for e in s.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.seq)]
    assert kinds[:1] == ["reconciling"] and "applying_policy" in kinds and kinds[-1] == "verdict"
    assert s.query(Decision).one().job_id == job_id
    s.close()
