"""Decision-agent contracts: tool results, the record_decision payload, the
wire shapes the frontend consumes (DecisionRead / AgentStep / PerceptionRead).

No ORM, no I/O. All numbers in these shapes are computed in Python; the
model only echoes them back and Python rejects any mismatch.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import Verdict
from app.domain.schemas.policies import CompiledRule
from app.domain.schemas.simulation import LineDecisionInput


class PerceptionRead(BaseModel):
    """Frontend contract: perception detail per line (from perception_results)."""

    noun_phrase: str
    observed_count: int
    max_visible: int
    track_ids: list[str] = Field(default_factory=list)
    damaged_track_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    footage_needed: str | None = None


class TrackRef(BaseModel):
    """A stored SAM track the agent may cite as evidence."""

    track_id: str
    first_frame: int | None = None
    last_frame: int | None = None


class AgentStep(BaseModel):
    seq: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None


class RecordDecisionLine(BaseModel):
    po_line_id: int
    po: int
    grn: int | None = None
    invoiced: int
    observed: int | None = None
    variance_pct: float | None = None
    rule_id: str | None = None
    clause: str | None = None
    evidence: list[str] = Field(default_factory=list)  # "track:<id>" / "frame:<n>"


class RecordDecisionPayload(BaseModel):
    verdict: Verdict
    amount_held_paise: int
    lines: list[RecordDecisionLine]
    summary_en: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)


class DecisionRead(BaseModel):
    """Frontend contract (+ optional source / fallback_reasons / stale / lines)."""

    verdict: Verdict
    amount_held_paise: int
    summary_en: str
    recommended_action: str
    model: str
    trace: list[AgentStep] = Field(default_factory=list)
    source: str = "agent"  # "agent" | "fallback"
    fallback_reasons: list[str] = Field(default_factory=list)
    stale: bool = False  # stored verdict/amount != current Python recompute
    lines: list[RecordDecisionLine] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """What the agent service persists (one decisions row)."""

    po_id: int
    delivery_id: int
    job_id: str | None = None
    verdict: Verdict
    amount_held_paise: int
    at_risk_paise: int = 0
    summary_en: str
    recommended_action: str
    model: str
    source: str
    fallback_reasons: list[str] = Field(default_factory=list)
    trace: list[AgentStep] = Field(default_factory=list)
    lines: list[RecordDecisionLine] = Field(default_factory=list)
    clauses: list[str] = Field(default_factory=list)
    variance_pct: float | None = None


class LineCaseFacts(BaseModel):
    po_line_id: int
    line_no: int
    sku: str
    description: str
    category: str
    unit: str
    facts: LineDecisionInput | None = None  # None: no observed evidence at all
    perception: PerceptionRead | None = None
    tracks: list[TrackRef] = Field(default_factory=list)


class CaseFacts(BaseModel):
    delivery_id: int
    po_id: int
    po_number: str
    vendor_name: str
    grn_number: str | None = None
    invoice_id: int | None = None
    invoice_number: str | None = None
    invoice_total_paise: int | None = None
    policy_version: str | None = None
    lines: list[LineCaseFacts]
    rules: list[CompiledRule] = Field(default_factory=list)


class ToolCall(BaseModel):
    name: str
    arguments: str  # JSON string, exactly as the API returned it
    call_id: str


class ToolTurn(BaseModel):
    """One model turn of the tool-calling loop (MODEL_NOTES §3)."""

    output_items: list[dict[str, Any]] = Field(default_factory=list)  # replayed verbatim
    calls: list[ToolCall] = Field(default_factory=list)
    output_text: str = ""


class VarianceResult(BaseModel):
    po_line_id: int
    po: int
    grn: int | None
    invoiced: int
    observed: int
    damaged: int
    variance_pct: float | None
    evidence_source: str
    evidence_quality: str | None
    unit_price_paise: int
    value_at_risk_paise: int


class RuleEvalResult(BaseModel):
    rule_id: str
    po_line_id: int
    clause: str
    action: str
    fired: bool
    why: str


class DebitNoteLine(BaseModel):
    po_line_id: int
    qty: int
    unit_price_paise: int
    amount_paise: int
    reason: str


class DebitNoteDraft(BaseModel):
    invoice_id: int
    invoice_number: str | None
    lines: list[DebitNoteLine]
    total_paise: int


class ToolCoverage(BaseModel):
    """Which tool calls actually succeeded -- the guard's source of truth."""

    variance_lines: set[int] = Field(default_factory=set)
    evaluated: set[tuple[str, int]] = Field(default_factory=set)  # (rule_id, po_line_id)
