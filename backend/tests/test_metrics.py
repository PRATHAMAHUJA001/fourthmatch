"""Pure aggregation math (domain/metrics.py, domain/policy_doc.py). No DB, no models."""
from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.enums import Verdict  # noqa: E402
from app.domain.metrics import (  # noqa: E402
    VERDICT_LABELS,
    confusion_matrix,
    discrepancy_rate_pct,
    discrepancy_types,
    held_by_vendor,
    latency_rows,
    mean_seconds,
    percentile,
    ratio,
    risk_score,
    trend_buckets,
    type_mix,
    vendor_risk,
    verdict_metrics,
)
from app.domain.money import format_inr  # noqa: E402
from app.domain.policy_doc import parse_policy  # noqa: E402
from app.domain.schemas.cases import CaseDetail, CaseLineRead, CaseSummary, CitedRule  # noqa: E402
from app.domain.schemas.dashboard import JobSpan, ModelCallStat  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures" / "dashboard_metrics.json").read_text())


def test_confusion_matrix_and_metrics_match_fixture() -> None:
    matrix = confusion_matrix([tuple(p) for p in FIX["confusion_pairs"]])
    assert matrix == FIX["expected_matrix"]
    by_label = {m.label.value: m for m in verdict_metrics(matrix)}
    for label, expected in FIX["expected_metrics"].items():
        got = by_label[label]
        assert got.support == expected["support"]
        for key in ("precision", "recall", "f1"):
            if key in expected:
                want = expected[key]
                assert (got.__getattribute__(key) is None) if want is None else got.__getattribute__(key) == pytest.approx(want)
    # F1 of approve: p=1.0, r=0.5 -> 2/3
    assert by_label["approve"].f1 == pytest.approx(2 / 3)
    assert [m.label for m in verdict_metrics(matrix)] == VERDICT_LABELS


def test_confusion_matrix_rejects_unknown_label() -> None:
    with pytest.raises(ValueError):
        confusion_matrix([("approve", "maybe")])


def test_f1_undefined_when_precision_and_recall_are_zero() -> None:
    matrix = confusion_matrix([("hold", "partial_pay")])
    by_label = {m.label.value: m for m in verdict_metrics(matrix)}
    assert by_label["partial_pay"].precision == 0.0
    assert by_label["partial_pay"].recall is None  # never occurs in truth
    assert by_label["hold"].recall == 0.0
    assert by_label["hold"].precision is None
    assert by_label["hold"].f1 is None


def test_percentile_linear_interpolation() -> None:
    values = FIX["percentile_values"]
    assert percentile(values, 50) == 30
    assert percentile(values, 95) == pytest.approx(48.0)
    assert percentile([7], 95) == 7
    assert percentile([], 50) is None
    assert percentile([5, 1, 3], 0) == 1
    with pytest.raises(ValueError):
        percentile([1], 101)


def test_latency_rows_exclude_cache_hits_and_null_latency() -> None:
    rows = {(r.model, r.role): r for r in latency_rows(ModelCallStat(**c) for c in FIX["model_calls"])}
    a = rows[("m-a", "understanding")]
    assert a.calls == 4  # every logged call counts
    assert a.p50_ms == 200.0 and a.p95_ms == 290.0  # live calls 100/200/300 only
    b = rows[("m-b", "policy_compile")]
    assert b.calls == 2 and b.p50_ms is None and b.p95_ms is None  # no live latency -> null, never 0
    assert latency_rows([]) == []


def test_mean_seconds_and_naive_datetimes() -> None:
    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    spans = [
        JobSpan(started_at=t0, finished_at=t0 + timedelta(seconds=40)),
        JobSpan(started_at=t0.replace(tzinfo=None), finished_at=(t0 + timedelta(seconds=61)).replace(tzinfo=None)),
    ]
    assert mean_seconds(spans) == 50.5
    assert mean_seconds([]) is None


def test_discrepancy_rate_and_ratio() -> None:
    assert discrepancy_rate_pct(4, 12) == 33.3
    assert discrepancy_rate_pct(0, 0) == 0.0
    assert ratio(3, 4) == 0.75
    assert ratio(1, 0) == 0.0
    assert risk_score(3, 1) == 33 and risk_score(0, 0) == 0


def test_trend_buckets_zero_fill_window_and_outside_events() -> None:
    cfg = FIX["trend"]
    events = [(date.fromisoformat(d), flag) for d, flag in cfg["events"]]
    trend = trend_buckets(events, date.fromisoformat(cfg["today"]))
    assert len(trend) == 30
    assert trend[0].date == date(2026, 10, 3) and trend[-1].date == date(2026, 11, 1)
    by_day = {p.date: p for p in trend}
    assert (by_day[date(2026, 11, 1)].deliveries, by_day[date(2026, 11, 1)].discrepancies) == (2, 1)
    assert (by_day[date(2026, 10, 30)].deliveries, by_day[date(2026, 10, 30)].discrepancies) == (1, 1)
    assert (by_day[date(2026, 10, 3)].deliveries, by_day[date(2026, 10, 3)].discrepancies) == (1, 0)
    assert sum(p.deliveries for p in trend) == 4  # 2026-10-02 and 2026-11-02 are outside the window
    assert by_day[date(2026, 10, 20)].deliveries == 0  # no data -> zero, not invented


def _summary(po_id: int, vendor: str, verdict: Verdict | None, held: int) -> CaseSummary:
    return CaseSummary(
        po_id=po_id, po_number=f"PO-{po_id}", vendor_id=1, vendor_name=vendor, status="received",
        order_date=date(2026, 10, 1), expected_date=date(2026, 10, 8), total_paise=1000,
        verdict=verdict, held_paise=held,
    )


def test_vendor_rollups_skip_undecided_and_sort() -> None:
    cases = [
        _summary(1, "A", Verdict.APPROVE, 0),
        _summary(2, "A", Verdict.PARTIAL_PAY, 5_000),
        _summary(3, "B", Verdict.HOLD, 9_000),
        _summary(4, "B", None, 0),
    ]
    held = held_by_vendor(cases)
    assert [(h.vendor_name, h.held_paise, h.cases) for h in held] == [("B", 9_000, 1), ("A", 5_000, 2)]
    risk = vendor_risk(cases)
    assert [(r.vendor_name, r.cases, r.discrepancies, r.risk_score) for r in risk] == [("B", 1, 1, 100), ("A", 2, 1, 50)]


def _line(**kw: object) -> CaseLineRead:
    base: dict[str, object] = dict(
        po_line_id=1, line_no=1, sku="S", description="d", category="cartons", unit="box", po_qty=14, grn_qty=14,
        invoiced_qty=14, observed_count=12, evidence_source="video", unit_price_paise=100, po_unit_price_paise=100,
        line_value_paise=1400,
    )
    base.update(kw)
    return CaseLineRead(**base)  # type: ignore[arg-type]


def _case(verdict: Verdict, line: CaseLineRead) -> CaseDetail:
    return CaseDetail(**_summary(1, "A", verdict, 0).model_dump(), lines=[line])


def test_discrepancy_types_from_evidence_and_cited_clauses() -> None:
    rule = CitedRule(rule_id="R", source_clause="4.2", source_text="t", action="partial_pay")
    short = _case(Verdict.PARTIAL_PAY, _line(cited_rules=[rule]))
    assert discrepancy_types(short) == ["grn_contradicted_by_video", "short_shipment_beyond_tolerance"]
    doc_only = _case(Verdict.HOLD, _line(evidence_source="document", observed_count=14,
                                         cited_rules=[CitedRule(rule_id="P", source_clause="5.1", source_text="t", action="hold")]))
    assert discrepancy_types(doc_only) == ["invoice_price_above_po"]
    clean = _case(Verdict.APPROVE, _line(observed_count=14))
    assert discrepancy_types(clean) == []
    weak = _case(Verdict.HUMAN_REVIEW, _line(observed_count=14, evidence_quality="insufficient"))
    assert discrepancy_types(weak) == ["insufficient_evidence"]
    mix = type_mix([short, doc_only, clean, weak])
    assert {m.type: m.count for m in mix} == {
        "grn_contradicted_by_video": 1, "short_shipment_beyond_tolerance": 1,
        "invoice_price_above_po": 1, "insufficient_evidence": 1,
    }


def test_parse_policy_committed_document() -> None:
    policy = parse_policy((ROOT / "data" / "policy" / "receiving_policy.md").read_text())
    assert policy.title == "Receiving and Payment-Hold Policy"
    assert policy.document_no == "FM-POL-PROC-001"
    assert policy.version == "1.0" and policy.effective_date == "2026-04-01"
    by_id = {c.clause_id: c for c in policy.clauses}
    assert by_id["4.2"].section == "Quantity verification"
    assert by_id["4.2"].text.startswith("The quantity tolerance for acceptance without escalation")
    assert by_id["3.3"].text.endswith("₹1,00,000.")
    assert format_inr(10000000) == "₹1,00,000"


def test_parse_policy_joins_continuation_lines() -> None:
    md = "# T\n**Version 2.1**\n## 1 Sec\n**1.1** first line\nsecond line\n\n**1.2** next\n"
    policy = parse_policy(md, policy_id=7)
    assert policy.id == 7 and policy.version == "2.1"
    assert [(c.clause_id, c.text) for c in policy.clauses] == [("1.1", "first line second line"), ("1.2", "next")]
