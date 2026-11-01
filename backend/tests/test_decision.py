"""domain/decision.py: THE decision function. Pure, no model calls."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.decision import (  # noqa: E402
    build_facts,
    decide_delivery,
    decide_line,
    disputed_paise,
    payable_qty,
)
from app.domain.enums import Verdict  # noqa: E402
from app.domain.schemas.policies import CompiledRule  # noqa: E402
from app.domain.schemas.simulation import LineDecisionInput  # noqa: E402


def _rule(rule_id: str, field: str, op: str, value: float, action: str, **kw: object) -> CompiledRule:
    return CompiledRule(
        rule_id=rule_id, goods_category=str(kw.get("cat", "all")),
        condition={"field": field, "op": op, "value": value},  # type: ignore[arg-type]
        action=action, signoff_role=kw.get("role"),  # type: ignore[arg-type]
        source_clause="4.2", source_text="x", ambiguity=None,
    )


def _line(**kw: object) -> LineDecisionInput:
    base = dict(
        po_line_id=1, goods_category="cartons", evidence_source="video",
        evidence_quality="reliable", observed_count=10, invoiced_qty=10, po_qty=10,
        grn_qty=10, damage_count=0, unit_price_paise=100_00, line_value_paise=1000_00,
    )
    base.update(kw)
    return LineDecisionInput(**base)  # type: ignore[arg-type]


HOLD_RULE = _rule("R-HOLD", "variance_pct", ">", 0.0, "hold")
SIGNOFF_RULE = _rule("R-SIGN", "variance_pct", ">", 0.0, "require_signoff", role="Stores Manager")
PARTIAL_RULE = _rule("R-PART", "damage_count", ">", 0.0, "partial_pay")
PRICE_HOLD_RULE = _rule("R-PRICE", "price_variance_pct", ">", 2.0, "hold")


def test_insufficient_evidence_forces_human_review_full_hold() -> None:
    v = decide_line(_line(evidence_quality="insufficient"), [])
    assert v.verdict == Verdict.HUMAN_REVIEW and v.held_paise == 1000_00


def test_hold_trumps_partial_and_holds_full_value() -> None:
    v = decide_line(_line(observed_count=8, damage_count=1), [HOLD_RULE, PARTIAL_RULE])
    assert v.verdict == Verdict.HOLD and v.held_paise == 1000_00
    assert v.triggered_rule_ids == ["R-HOLD", "R-PART"]


def test_require_signoff_is_human_review() -> None:
    v = decide_line(_line(observed_count=8), [SIGNOFF_RULE])
    assert v.verdict == Verdict.HUMAN_REVIEW and v.held_paise == 1000_00


def test_partial_pay_holds_only_disputed_portion() -> None:
    # payable = min(po 10, observed 8 - damage 1, invoiced 10) = 7; disputed 3 * ₹100
    v = decide_line(_line(observed_count=8, damage_count=1), [PARTIAL_RULE])
    assert v.verdict == Verdict.PARTIAL_PAY and v.held_paise == 300_00


def test_signoff_and_partial_pay_both_fire_partial_amounts_role_recorded() -> None:
    # Clause 4.2 compiled as two rules on the same shortage: require_signoff
    # (Stores Manager, before GRN closure) + partial_pay (pay received only).
    # payable = min(po 10, observed 8, invoiced 10) = 8; disputed 2 * ₹100.
    partial_variance = _rule("R-PART", "variance_pct", ">", 0.0, "partial_pay")
    v = decide_line(_line(observed_count=8), [SIGNOFF_RULE, partial_variance])
    assert v.verdict == Verdict.PARTIAL_PAY
    assert v.held_paise == 200_00 and v.at_risk_paise == 200_00
    assert v.triggered_rule_ids == ["R-PART", "R-SIGN"]
    assert v.signoff_roles == ["Stores Manager"]
    d = decide_delivery([_line(observed_count=8)], [SIGNOFF_RULE, partial_variance])
    assert d.verdict == Verdict.PARTIAL_PAY and d.signoff_roles == ["Stores Manager"]


def test_partial_pay_capped_at_line_value() -> None:
    v = decide_line(_line(observed_count=0, damage_count=50), [PARTIAL_RULE])
    assert v.held_paise == 1000_00


def test_no_trigger_approves() -> None:
    v = decide_line(_line(), [HOLD_RULE, PARTIAL_RULE])
    assert v.verdict == Verdict.APPROVE and v.held_paise == 0


def test_delivery_aggregation_severity_sum_union() -> None:
    lines = [
        _line(po_line_id=1, observed_count=8, damage_count=1),  # hold via HOLD_RULE
        _line(po_line_id=2, evidence_quality="insufficient"),  # human_review
    ]
    d = decide_delivery(lines, [HOLD_RULE, PARTIAL_RULE])
    assert d.verdict == Verdict.HOLD  # hold > human_review > partial_pay > approve
    assert d.held_paise == 1000_00 + 1000_00
    assert d.triggered_rule_ids == ["R-HOLD", "R-PART"]


def test_build_facts_computes_both_variances_in_python() -> None:
    facts = build_facts(_line(po_qty=14, invoiced_qty=14, observed_count=12))
    assert facts.variance_pct is not None and abs(facts.variance_pct - 14.2857) < 0.01
    assert facts.variance_vs_invoice_pct is not None
    assert abs(facts.variance_vs_invoice_pct - 14.2857) < 0.01
    facts2 = build_facts(_line(po_qty=10, invoiced_qty=12, observed_count=10))
    assert facts2.variance_pct == 0.0
    assert facts2.variance_vs_invoice_pct is not None
    assert abs(facts2.variance_vs_invoice_pct - 16.6667) < 0.01


@pytest.mark.parametrize(
    ("kw", "expected_payable", "expected_held"),
    [
        # shortage: po 10, observed 8, invoiced 10 -> payable 8, disputed 2
        (dict(observed_count=8), 8, 200_00),
        # damage: observed 10, damaged 2 -> payable 8, disputed 2
        (dict(damage_count=2), 8, 200_00),
        # over-invoice: received 10, invoiced 12 -> payable 10, disputed 2
        (dict(invoiced_qty=12, line_value_paise=1200_00), 10, 200_00),
        # over-PO: received/invoiced 12 against PO 10 -> payable 10, disputed 2
        (dict(observed_count=12, invoiced_qty=12, line_value_paise=1200_00), 10, 200_00),
        # combination: po 100, observed 90, damaged 5, invoiced 110 -> payable 85
        (dict(po_qty=100, observed_count=90, damage_count=5, invoiced_qty=110,
              line_value_paise=110 * 100_00), 85, 25 * 100_00),
        # damage exceeds observed: payable floors at 0, held caps at line value
        (dict(observed_count=3, damage_count=9), 0, 1000_00),
    ],
)
def test_payable_quantity_rule(kw: dict, expected_payable: int, expected_held: int) -> None:
    line = _line(**kw)
    assert payable_qty(line) == expected_payable
    assert disputed_paise(line) == expected_held


def test_build_facts_new_fields() -> None:
    facts = build_facts(_line(
        po_qty=100, invoiced_qty=112, observed_count=100,
        unit_price_paise=108_00, po_unit_price_paise=100_00, duplicate_invoice=True,
    ))
    assert facts.price_variance_pct == pytest.approx(8.0)
    assert facts.invoiced_vs_po_pct == pytest.approx(12.0)
    assert facts.duplicate_invoice is True


def test_hold_at_risk_full_line_for_non_price_hold() -> None:
    v = decide_line(_line(observed_count=8), [HOLD_RULE])
    assert v.verdict == Verdict.HOLD
    assert v.held_paise == 1000_00 and v.at_risk_paise == 1000_00


def test_price_hold_at_risk_is_price_difference_only() -> None:
    # invoice ₹110 vs PO ₹100, qty 10: held = full ₹1,100; at risk = ₹10 x 10
    v = decide_line(
        _line(unit_price_paise=110_00, po_unit_price_paise=100_00, line_value_paise=1100_00),
        [PRICE_HOLD_RULE],
    )
    assert v.verdict == Verdict.HOLD
    assert v.held_paise == 1100_00 and v.at_risk_paise == 100_00


def test_human_review_at_risk_is_zero_not_a_loss() -> None:
    v = decide_line(_line(evidence_quality="insufficient"), [])
    assert v.held_paise == 1000_00 and v.at_risk_paise == 0
    v2 = decide_line(_line(observed_count=8), [SIGNOFF_RULE])
    assert v2.verdict == Verdict.HUMAN_REVIEW and v2.held_paise == 1000_00 and v2.at_risk_paise == 0


def test_partial_pay_at_risk_equals_held() -> None:
    v = decide_line(_line(observed_count=8, damage_count=1), [PARTIAL_RULE])
    assert v.held_paise == 300_00 and v.at_risk_paise == 300_00


def test_no_banned_verdict_vocabulary_anywhere() -> None:
    banned = "hold_" + "payment"  # spelled split so this guard does not trip itself
    roots = [ROOT / "backend" / "app", ROOT / "docs", ROOT / "scripts"]
    offenders = [
        str(p) for root in roots for p in root.rglob("*")
        if p.is_file() and p.suffix in {".py", ".md"} and banned in p.read_text(errors="ignore")
    ]
    assert offenders == []
    assert {v.value for v in Verdict} == {"approve", "partial_pay", "hold", "human_review"}
