"""Pure logic for the payment-decision agent. No I/O, no LLM, no framework.

Every number here comes from domain.decision (the single decision function)
and domain.rules (the single rule evaluator); this module only assembles
their outputs for the agent's tools, checks the agent's final payload
against them (the guards), and builds the deterministic fallback decision.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.decision import (
    build_facts,
    decide_delivery,
    disputed_paise,
    payable_qty,
)
from app.domain.enums import EvidenceQuality, Verdict
from app.domain.money import format_inr
from app.domain.rules import evaluate_rule, is_category_specific, rule_applies_to_category
from app.domain.schemas.decision_agent import (
    CaseFacts,
    DebitNoteDraft,
    DebitNoteLine,
    LineCaseFacts,
    RecordDecisionLine,
    RecordDecisionPayload,
    RuleEvalResult,
    ToolCoverage,
    VarianceResult,
)
from app.domain.schemas.policies import CompiledRule
from app.domain.schemas.simulation import DeliveryVerdict, LineDecisionInput

_ACTION_RANK = {"hold": 0, "require_signoff": 1, "partial_pay": 2, "approve": 3}
_VARIANCE_TOLERANCE = 0.011


def evaluable_lines(facts: CaseFacts) -> list[LineCaseFacts]:
    """Lines that have an observed quantity (video or GRN)."""
    return [ln for ln in facts.lines if ln.facts is not None]


def line_inputs(facts: CaseFacts) -> list[LineDecisionInput]:
    return [ln.facts for ln in facts.lines if ln.facts is not None]


def recompute(facts: CaseFacts) -> DeliveryVerdict:
    """THE verdict for the case: domain.decision over approved rules."""
    return decide_delivery(line_inputs(facts), facts.rules)


def _round_variance(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def variance_result(line: LineCaseFacts) -> VarianceResult:
    inp = line.facts
    if inp is None:
        raise ValueError(f"po_line_id {line.po_line_id} has no observed evidence")
    return VarianceResult(
        po_line_id=line.po_line_id,
        po=inp.po_qty,
        grn=inp.grn_qty,
        invoiced=inp.invoiced_qty,
        observed=inp.observed_count,
        damaged=inp.damage_count,
        variance_pct=_round_variance(build_facts(inp).variance_pct),
        evidence_source=inp.evidence_source,
        evidence_quality=inp.evidence_quality,
        unit_price_paise=inp.unit_price_paise,
        value_at_risk_paise=disputed_paise(inp),
    )


def rules_for_category(rules: list[CompiledRule], category: str) -> list[CompiledRule]:
    return [r for r in rules if rule_applies_to_category(r, category)]


def applicable_pairs(facts: CaseFacts) -> set[tuple[str, int]]:
    return {
        (rule.rule_id, ln.po_line_id)
        for ln in evaluable_lines(facts)
        for rule in rules_for_category(facts.rules, ln.category)
    }


def evaluate_rule_for_line(rule: CompiledRule, line: LineCaseFacts) -> RuleEvalResult:
    inp = line.facts
    if inp is None:
        raise ValueError(f"po_line_id {line.po_line_id} has no observed evidence")
    outcome = evaluate_rule(rule, build_facts(inp))
    why = f"{outcome.reason}: {outcome.field}={outcome.observed_value}"
    return RuleEvalResult(
        rule_id=rule.rule_id,
        po_line_id=line.po_line_id,
        clause=rule.source_clause,
        action=rule.action,
        fired=outcome.triggered,
        why=why,
    )


def draft_debit_note(
    facts: CaseFacts, invoice_id: int, items: list[tuple[int, str]]
) -> DebitNoteDraft:
    """Debit note for the disputed portion of the named lines (Python money)."""
    if facts.invoice_id is None or invoice_id != facts.invoice_id:
        raise ValueError(f"unknown invoice_id {invoice_id}")
    by_id = {ln.po_line_id: ln for ln in evaluable_lines(facts)}
    lines: list[DebitNoteLine] = []
    for po_line_id, reason in items:
        line = by_id.get(po_line_id)
        if line is None or line.facts is None:
            raise ValueError(f"unknown po_line_id {po_line_id}")
        inp = line.facts
        qty = inp.invoiced_qty - payable_qty(inp)
        if qty <= 0:
            continue
        lines.append(
            DebitNoteLine(
                po_line_id=po_line_id,
                qty=qty,
                unit_price_paise=inp.unit_price_paise,
                amount_paise=disputed_paise(inp),
                reason=reason,
            )
        )
    return DebitNoteDraft(
        invoice_id=invoice_id,
        invoice_number=facts.invoice_number,
        lines=lines,
        total_paise=sum(ln.amount_paise for ln in lines),
    )


def pick_rule(rules: list[CompiledRule], fired_ids: list[str]) -> CompiledRule | None:
    """Most specific fired rule: category-specific first, then most severe action."""
    fired = [r for r in rules if r.rule_id in set(fired_ids)]
    if not fired:
        return None
    return sorted(
        fired,
        key=lambda r: (0 if is_category_specific(r) else 1, _ACTION_RANK.get(r.action, 9), r.rule_id),
    )[0]


# ---------------------------------------------------------------- evidence


def parse_evidence(item: str) -> tuple[str, str]:
    """('track', id) | ('frame', n) | ('bare', id)."""
    text = item.strip()
    if text.startswith("track:"):
        return "track", text[len("track:"):].strip()
    if text.startswith("frame:"):
        return "frame", text[len("frame:"):].strip()
    return "bare", text


def _check_evidence(line: LineCaseFacts, evidence: list[str]) -> list[str]:
    errors: list[str] = []
    track_ids = {t.track_id for t in line.tracks}
    firsts = [t.first_frame for t in line.tracks if t.first_frame is not None]
    lasts = [t.last_frame for t in line.tracks if t.last_frame is not None]
    lo, hi = (min(firsts), max(lasts)) if firsts and lasts else (None, None)
    for item in evidence:
        kind, value = parse_evidence(item)
        if kind in ("track", "bare"):
            if value not in track_ids:
                errors.append(f"line {line.po_line_id}: unknown track_id {value!r}")
        else:
            try:
                frame = int(value)
            except ValueError:
                errors.append(f"line {line.po_line_id}: bad frame index {value!r}")
                continue
            if lo is None or hi is None or not lo <= frame <= hi:
                errors.append(f"line {line.po_line_id}: unknown frame_index {frame}")
    if line.facts is not None and line.facts.evidence_source == "video" and not evidence:
        errors.append(f"line {line.po_line_id}: video line must cite track IDs and a frame index")
    return errors


# ------------------------------------------------------------------ guards


class GuardResult(BaseModel):
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    payload: RecordDecisionPayload
    expected: DeliveryVerdict


def validate_payload(
    payload: RecordDecisionPayload, facts: CaseFacts, coverage: ToolCoverage
) -> GuardResult:
    """Python-side checks on the agent's record_decision payload.

    errors -> reject. A verdict that disagrees with the Python recompute while
    any line has insufficient evidence is overridden (human_review is forced,
    never approve) and noted instead of rejected.
    """
    expected = recompute(facts)
    errors: list[str] = []
    notes: list[str] = []
    lines = {ln.po_line_id: ln for ln in evaluable_lines(facts)}

    for po_line_id in sorted(lines):
        if po_line_id not in coverage.variance_lines:
            errors.append(f"compute_variance was not called for po_line_id {po_line_id}")
    for rule_id, po_line_id in sorted(applicable_pairs(facts) - coverage.evaluated):
        errors.append(f"evaluate_rule was not called for rule_id {rule_id} on po_line_id {po_line_id}")

    cited_lines = [ln.po_line_id for ln in payload.lines]
    for po_line_id in cited_lines:
        if po_line_id not in lines:
            errors.append(f"unknown po_line_id {po_line_id}")
    missing = sorted(set(lines) - set(cited_lines))
    if missing:
        errors.append(f"decision omits po_line_ids {missing}")
    if len(cited_lines) != len(set(cited_lines)):
        errors.append("decision cites a po_line_id more than once")

    rules_by_id = {r.rule_id: r for r in facts.rules}
    fired_by_line = {lv.po_line_id: set(lv.triggered_rule_ids) for lv in expected.lines}
    for entry in payload.lines:
        line = lines.get(entry.po_line_id)
        if line is None or line.facts is None:
            continue
        errors.extend(_check_line_numbers(entry, line.facts))
        if entry.rule_id is not None:
            rule = rules_by_id.get(entry.rule_id)
            if rule is None:
                errors.append(f"line {entry.po_line_id}: unknown rule_id {entry.rule_id!r}")
            else:
                if entry.rule_id not in fired_by_line.get(entry.po_line_id, set()):
                    errors.append(f"line {entry.po_line_id}: rule_id {entry.rule_id!r} did not fire")
                if entry.clause != rule.source_clause:
                    errors.append(
                        f"line {entry.po_line_id}: clause must be {rule.source_clause!r} for {entry.rule_id!r}"
                    )
        elif fired_by_line.get(entry.po_line_id):
            errors.append(f"line {entry.po_line_id}: a rule fired but rule_id is null")
        errors.extend(_check_evidence(line, entry.evidence))

    adjusted = payload
    insufficient = any(
        ln.facts is not None and ln.facts.evidence_quality == EvidenceQuality.INSUFFICIENT.value
        for ln in lines.values()
    )
    if payload.verdict != expected.verdict:
        if insufficient:
            notes.append(
                f"verdict {payload.verdict.value} overridden to {expected.verdict.value}: "
                "insufficient evidence can never be approved"
            )
            adjusted = payload.model_copy(update={"verdict": expected.verdict})
        else:
            errors.append(f"verdict {payload.verdict.value!r} does not match policy outcome")
    if payload.amount_held_paise != expected.held_paise:
        errors.append(
            f"amount_held_paise {payload.amount_held_paise} is wrong; "
            f"the Python recompute is {expected.held_paise}"
        )
    return GuardResult(errors=errors, notes=notes, payload=adjusted, expected=expected)


def _check_line_numbers(entry: RecordDecisionLine, inp: LineDecisionInput) -> list[str]:
    errors: list[str] = []
    want_var = _round_variance(build_facts(inp).variance_pct)
    checks: list[tuple[str, object, object]] = [
        ("po", entry.po, inp.po_qty),
        ("grn", entry.grn, inp.grn_qty),
        ("invoiced", entry.invoiced, inp.invoiced_qty),
        ("observed", entry.observed, inp.observed_count),
    ]
    for name, got, want in checks:
        if got != want:
            errors.append(f"line {entry.po_line_id}: {name} is {got}, tools say {want}")
    if (entry.variance_pct is None) != (want_var is None) or (
        entry.variance_pct is not None
        and want_var is not None
        and abs(entry.variance_pct - want_var) > _VARIANCE_TOLERANCE
    ):
        errors.append(f"line {entry.po_line_id}: variance_pct is {entry.variance_pct}, tools say {want_var}")
    return errors


# --------------------------------------------------------------- fallback

_ACTIONS = {
    Verdict.APPROVE: "Release payment in full.",
    Verdict.PARTIAL_PAY: "Pay the undisputed portion now and raise a debit note for the disputed amount.",
    Verdict.HOLD: "Hold payment and ask the vendor to correct the invoice or credit the difference.",
    Verdict.HUMAN_REVIEW: "Route to a finance manager: the evidence is not strong enough to pay or reject.",
}


def fallback_payload(facts: CaseFacts) -> RecordDecisionPayload:
    """Deterministic decision straight from domain.decision (no model)."""
    expected = recompute(facts)
    rules_by_id = {r.rule_id: r for r in facts.rules}
    verdict_by_line = {lv.po_line_id: lv for lv in expected.lines}
    lines: list[RecordDecisionLine] = []
    for ln in evaluable_lines(facts):
        inp = ln.facts
        assert inp is not None  # evaluable_lines guarantees it
        lv = verdict_by_line[ln.po_line_id]
        rule = pick_rule(facts.rules, lv.triggered_rule_ids)
        damaged = set(ln.perception.damaged_track_ids) if ln.perception else set()
        cited = [t for t in ln.tracks if t.track_id in damaged] or ln.tracks
        evidence = [f"track:{t.track_id}" for t in cited]
        starts = [t.first_frame for t in cited if t.first_frame is not None]
        if starts:
            evidence.append(f"frame:{min(starts)}")
        lines.append(
            RecordDecisionLine(
                po_line_id=ln.po_line_id,
                po=inp.po_qty,
                grn=inp.grn_qty,
                invoiced=inp.invoiced_qty,
                observed=inp.observed_count,
                variance_pct=_round_variance(build_facts(inp).variance_pct),
                rule_id=rule.rule_id if rule else None,
                clause=rules_by_id[rule.rule_id].source_clause if rule else None,
                evidence=evidence,
            )
        )
    clauses = sorted({ln.clause for ln in lines if ln.clause})
    ref = facts.invoice_number or facts.po_number
    first = f"Invoice {ref} is {expected.verdict.value.replace('_', ' ')}"
    if expected.held_paise:
        first += f" with {format_inr(expected.held_paise)} held"
    if clauses:
        first += f" under policy clause {', '.join(clauses)}"
    summary = f"{first}. This is the automatic policy result because the AI agent's answer could not be verified."
    return RecordDecisionPayload(
        verdict=expected.verdict,
        amount_held_paise=expected.held_paise,
        lines=lines,
        summary_en=summary,
        recommended_action=_ACTIONS[expected.verdict],
    )


# ---------------------------------------------------------- discrepancies

_QUANTITY_FIELDS = {"variance_pct", "variance_vs_invoice_pct"}


def discrepancy_types(line: LineDecisionInput, fired_fields: set[str]) -> list[str]:
    """Discrepancy tags derived only from computed facts + fired rule fields."""
    found: list[str] = []
    if (
        line.evidence_source == "video"
        and line.grn_qty is not None
        and line.grn_qty != line.observed_count
    ):
        found.append("grn_contradicted_by_video")
    if fired_fields & _QUANTITY_FIELDS:
        found.append("short_shipment_beyond_tolerance")
    if line.damage_count > 0 and line.invoiced_qty > line.observed_count - line.damage_count:
        found.append("damaged_units_invoiced")
    po_price = line.po_unit_price_paise if line.po_unit_price_paise is not None else line.unit_price_paise
    if line.unit_price_paise > po_price:
        found.append("invoice_price_above_po")
    if line.invoiced_qty > line.po_qty:
        found.append("invoice_qty_exceeds_po")
    if line.duplicate_invoice:
        found.append("duplicate_invoice_number")
    return found
