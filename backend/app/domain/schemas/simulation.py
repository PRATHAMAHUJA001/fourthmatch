"""Simulation + decision contracts crossing services -> api. No ORM, no I/O.

domain/decision.py is THE decision function for the whole app: it consumes
these shapes and returns verdicts. Callers (simulation today, the Day-3
decision agent tomorrow) supply precomputed facts and money in paise; they
never compute verdicts themselves.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import Verdict
from app.domain.schemas.policies import ApproverRoute, CompiledRule


class SimulatePolicyRequest(BaseModel):
    policy_text: str = Field(min_length=1)
    policy_version: str | None = None  # draft label; defaults to the text's **Version x**


class DraftRule(BaseModel):
    """One in-memory compiled rule. Never persisted, never approved."""

    rule: CompiledRule
    validation_errors: list[str] = Field(default_factory=list)


class DraftCompileResult(BaseModel):
    policy_version: str
    clauses_seen: int
    skipped_non_rule: int
    invalid: int
    ambiguous: int
    compiled: int = 0  # model calls made (cache misses, both compile steps)
    cache_hits: int = 0
    retries: int = 0  # clauses retried once after validation failure
    approver_routes: list[ApproverRoute] = Field(default_factory=list)  # routing, not rules
    rules: list[DraftRule] = Field(default_factory=list)  # valid + invalid, in clause order


class LineDecisionInput(BaseModel):
    """Everything decide_line needs for one PO line, precomputed in Python."""

    po_line_id: int
    goods_category: str
    evidence_source: str  # "video" | "document"
    evidence_quality: str | None = None  # "reliable" | "insufficient" | None (document lines)
    observed_count: int
    invoiced_qty: int
    po_qty: int
    grn_qty: int | None = None
    damage_count: int = 0
    unit_price_paise: int  # invoice unit price; line_value = invoiced_qty * this
    po_unit_price_paise: int | None = None  # PO unit price (defaults to invoice price)
    duplicate_invoice: bool = False  # DB lookup by caller: an EARLIER-booked invoice
    # with the same vendor + invoice_number exists
    line_value_paise: int


class LineVerdict(BaseModel):
    po_line_id: int
    evidence_source: str
    verdict: Verdict
    held_paise: int  # cash actually withheld
    at_risk_paise: int = 0  # value genuinely at risk (see domain/decision.py)
    triggered_rule_ids: list[str] = Field(default_factory=list)
    signoff_roles: list[str] = Field(default_factory=list)  # roles whose signoff a triggered rule requires


class DeliveryVerdict(BaseModel):
    """Verdict for one evaluation unit (a PO, with its delivery if any)."""

    verdict: Verdict
    held_paise: int
    at_risk_paise: int = 0
    triggered_rule_ids: list[str] = Field(default_factory=list)
    signoff_roles: list[str] = Field(default_factory=list)
    lines: list[LineVerdict] = Field(default_factory=list)


class LineDiff(BaseModel):
    po_line_id: int
    evidence_source: str
    before_verdict: Verdict
    after_verdict: Verdict
    before_held_paise: int
    after_held_paise: int


class PoVerdictDiff(BaseModel):
    po_id: int
    po_number: str
    delivery_id: int | None = None
    before_verdict: Verdict
    after_verdict: Verdict
    before_held_paise: int
    after_held_paise: int
    held_delta_paise: int
    before_triggered_rule_ids: list[str] = Field(default_factory=list)
    after_triggered_rule_ids: list[str] = Field(default_factory=list)
    lines: list[LineDiff] = Field(default_factory=list)


class DriftItem(BaseModel):
    """A stored Decision that disagrees with the recomputed baseline.

    The diff never reads stored decisions; drift is reported separately so a
    stale or hand-edited decision is visible instead of silently trusted.
    """

    po_id: int
    po_number: str
    delivery_id: int | None = None
    stored_decision_id: int
    stored_verdict: str
    stored_amount_at_risk_paise: int
    baseline_verdict: Verdict
    baseline_held_paise: int


class HeldTotals(BaseModel):
    held_before_paise: int
    held_after_paise: int
    held_delta_paise: int
    held_before_inr: str
    held_after_inr: str


class EvidenceSourceTotals(BaseModel):
    evidence_source: str  # "video" | "document"
    lines: int
    held_before_paise: int
    held_after_paise: int
    held_delta_paise: int


class PolicySimulationResult(BaseModel):
    policy_version: str  # baseline {id}: its APPROVED rules, recomputed
    draft_policy_version: str
    draft_rules: list[DraftRule] = Field(default_factory=list)
    draft_invalid: int
    draft_ambiguous: int
    draft_skipped_non_rule: int
    draft_compiled: int  # model calls made compiling the draft (cache misses)
    draft_cache_hits: int
    draft_retries: int = 0  # draft clauses retried once after validation failure
    baseline_approved_rules: int
    pos_evaluated: int
    lines_evaluated: int
    lines_skipped: int  # neither perception result nor GRN line: no observed qty exists
    changed: list[PoVerdictDiff] = Field(default_factory=list)
    unchanged_count: int
    drift: list[DriftItem] = Field(default_factory=list)
    totals: HeldTotals
    totals_by_evidence_source: list[EvidenceSourceTotals] = Field(default_factory=list)
