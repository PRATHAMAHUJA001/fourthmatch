"""THE decision function for the whole app. Pure Python, no I/O, no LLM.

Every verdict in FourthMatch comes from here. The Day-3 decision agent (and
the policy simulator) must call decide_delivery() and may not compute
verdicts itself: callers precompute facts and paise, this module maps rule
outcomes to a verdict and a held amount.

Per line (most severe triggered action wins, in this order):
  evidence_quality == "insufficient" -> human_review, held = full line value
  any triggered "hold"            -> hold,          held = full line value
  "partial_pay" + "require_signoff" both triggered
                                  -> partial_pay,   held = disputed portion,
                                     signoff role(s) recorded on the verdict
                                     (the undisputed portion is releasable;
                                     only the shortfall waits for signoff)
  any triggered "require_signoff" -> human_review,  held = full line value
  any triggered "partial_pay"     -> partial_pay,   held = disputed portion
  otherwise                       -> approve,       held = 0

held_paise (cash actually withheld) and at_risk_paise (value genuinely at
risk) are different numbers and both are returned:
  hold (price rule)  held = full line value,
                     at_risk = (inv_price - po_price) * invoiced_qty
  hold (duplicate or any other hold)
                     held = full line value, at_risk = full line value
  partial_pay        held = at_risk = disputed portion (below)
  human_review       held = full line value, at_risk = 0 (unknown, not a loss)
  approve            held = at_risk = 0

Disputed portion (Python only, ONE payable-quantity rule for every cause):
  payable_qty    = min(po_qty, observed_count - damage_count, invoiced_qty),
                   floored at 0
  disputed_paise = (invoiced_qty - payable_qty) * unit_price,
                   capped at the invoiced line value
Shortage, damage, over-invoice and over-PO all fall out of this one formula.

Delivery/PO aggregation: verdict = most severe line
(hold > human_review > partial_pay > approve), held = SUM of line held,
triggered_rule_ids = union over lines.
"""

from __future__ import annotations

from app.domain.enums import EvidenceQuality, Verdict
from app.domain.rules import evaluate_rules
from app.domain.schemas.policies import CompiledRule, RuleFacts
from app.domain.schemas.simulation import DeliveryVerdict, LineDecisionInput, LineVerdict

_SEVERITY: dict[Verdict, int] = {
    Verdict.APPROVE: 0,
    Verdict.PARTIAL_PAY: 1,
    Verdict.HUMAN_REVIEW: 2,
    Verdict.HOLD: 3,
}


def payable_qty(line: LineDecisionInput) -> int:
    """Units payable for a line: never more than ordered, received-undamaged,
    or invoiced; never negative. The single disputed-quantity rule."""
    return max(0, min(line.po_qty, line.observed_count - line.damage_count, line.invoiced_qty))


def disputed_paise(line: LineDecisionInput) -> int:
    """Value of the invoiced-but-not-payable portion, capped at line value."""
    return min((line.invoiced_qty - payable_qty(line)) * line.unit_price_paise, line.line_value_paise)


def build_facts(line: LineDecisionInput) -> RuleFacts:
    """Assemble rule facts for one line. All arithmetic is Python, here."""
    variance_pct = (
        (line.po_qty - line.observed_count) / line.po_qty * 100 if line.po_qty else None
    )
    variance_vs_invoice_pct = (
        (line.invoiced_qty - line.observed_count) / line.invoiced_qty * 100
        if line.invoiced_qty
        else None
    )
    po_price = line.po_unit_price_paise if line.po_unit_price_paise is not None else line.unit_price_paise
    price_variance_pct = (
        (line.unit_price_paise - po_price) / po_price * 100 if po_price else None
    )
    invoiced_vs_po_pct = (
        (line.invoiced_qty - line.po_qty) / line.po_qty * 100 if line.po_qty else None
    )
    return RuleFacts(
        observed_count=float(line.observed_count),
        invoiced_qty=float(line.invoiced_qty),
        po_qty=float(line.po_qty),
        grn_qty=float(line.grn_qty) if line.grn_qty is not None else None,
        damage_count=float(line.damage_count),
        unit_price=line.unit_price_paise / 100,
        line_value=line.line_value_paise / 100,
        goods_category=line.goods_category,
        variance_pct=variance_pct,
        variance_vs_invoice_pct=variance_vs_invoice_pct,
        price_variance_pct=price_variance_pct,
        invoiced_vs_po_pct=invoiced_vs_po_pct,
        duplicate_invoice=line.duplicate_invoice,
    )


def price_at_risk_paise(line: LineDecisionInput) -> int:
    """Exposure on a price hold: only the price difference, not the line."""
    po_price = line.po_unit_price_paise if line.po_unit_price_paise is not None else line.unit_price_paise
    return max(0, min((line.unit_price_paise - po_price) * line.invoiced_qty, line.line_value_paise))


def decide_line(line: LineDecisionInput, rules: list[CompiledRule]) -> LineVerdict:
    """Verdict for one PO line from precomputed facts + compiled rules."""
    outcomes = evaluate_rules(rules, build_facts(line))
    triggered = [o for o in outcomes if o.triggered]
    triggered_ids = sorted(o.rule_id for o in triggered)
    actions = {o.action for o in triggered}
    rule_by_id = {r.rule_id: r for r in rules}
    signoff_roles = sorted({
        role for o in triggered
        if o.action == "require_signoff" and o.rule_id in rule_by_id
        if (role := (rule_by_id[o.rule_id].signoff_role or "").strip())
    })

    if line.evidence_quality == EvidenceQuality.INSUFFICIENT.value:
        verdict, held, at_risk = Verdict.HUMAN_REVIEW, line.line_value_paise, 0
    elif "hold" in actions:
        verdict, held = Verdict.HOLD, line.line_value_paise
        price_held = any(o.action == "hold" and o.field == "price_variance_pct" for o in triggered)
        at_risk = price_at_risk_paise(line) if price_held else line.line_value_paise
    elif "partial_pay" in actions and "require_signoff" in actions:
        # Payment is released for the received portion; only the disputed
        # shortfall is withheld, pending the recorded signoff.
        held = at_risk = disputed_paise(line)
        verdict = Verdict.PARTIAL_PAY
    elif "require_signoff" in actions:
        verdict, held, at_risk = Verdict.HUMAN_REVIEW, line.line_value_paise, 0
    elif "partial_pay" in actions:
        held = at_risk = disputed_paise(line)
        verdict = Verdict.PARTIAL_PAY
    else:
        verdict, held, at_risk = Verdict.APPROVE, 0, 0

    return LineVerdict(
        po_line_id=line.po_line_id,
        evidence_source=line.evidence_source,
        verdict=verdict,
        held_paise=held,
        at_risk_paise=at_risk,
        triggered_rule_ids=triggered_ids,
        signoff_roles=signoff_roles,
    )


def decide_delivery(
    lines: list[LineDecisionInput], rules: list[CompiledRule]
) -> DeliveryVerdict:
    """Aggregate line verdicts: most severe wins, held sums, ids union."""
    line_verdicts = [decide_line(line, rules) for line in lines]
    verdict = Verdict.APPROVE
    for lv in line_verdicts:
        if _SEVERITY[lv.verdict] > _SEVERITY[verdict]:
            verdict = lv.verdict
    return DeliveryVerdict(
        verdict=verdict,
        held_paise=sum(lv.held_paise for lv in line_verdicts),
        at_risk_paise=sum(lv.at_risk_paise for lv in line_verdicts),
        triggered_rule_ids=sorted({r for lv in line_verdicts for r in lv.triggered_rule_ids}),
        signoff_roles=sorted({r for lv in line_verdicts for r in lv.signoff_roles}),
        lines=line_verdicts,
    )
