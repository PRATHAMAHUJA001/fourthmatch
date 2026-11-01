"""Case read contracts: PO vs GRN vs invoice vs SAM, with the verdict.

Design, rationale, and file/test traceability: docs/CASES.md.

A case is one purchase order decided live through domain.decision from
approved compiled rules. ``verdict is None`` means no line had observed
evidence (neither perception nor GRN) -- it is never a fabricated approve.
All money is integer paise; all counts and variances are computed in Python.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.domain.enums import Verdict
from app.domain.schemas.decision_agent import DecisionRead, PerceptionRead


class CitedRule(BaseModel):
    """One triggered rule, resolved in Python from the rule row. IDs that do
    not resolve to an approved rule are dropped, never rendered."""

    rule_id: str
    source_clause: str
    source_text: str
    action: str


class CaseLineRead(BaseModel):
    po_line_id: int
    line_no: int
    sku: str
    description: str
    category: str
    unit: str
    po_qty: int
    grn_qty: int | None = None
    invoiced_qty: int
    observed_count: int | None = None  # SAM count (video) or GRN qty (document)
    damage_count: int = 0
    evidence_source: str  # "video" | "document" | "none"
    evidence_quality: str | None = None  # reliable | insufficient | None
    unit_price_paise: int  # invoice unit price
    po_unit_price_paise: int
    line_value_paise: int  # invoiced_qty * invoice unit price
    variance_pct: float | None = None  # (po_qty - observed) / po_qty * 100
    verdict: Verdict | None = None
    held_paise: int = 0
    at_risk_paise: int = 0
    signoff_roles: list[str] = Field(default_factory=list)
    cited_rules: list[CitedRule] = Field(default_factory=list)
    perception: PerceptionRead | None = None  # SAM-backed detail (video lines only)


class CaseSummary(BaseModel):
    po_id: int
    po_number: str
    vendor_id: int
    vendor_name: str
    scenario_id: str | None = None
    status: str
    order_date: date
    expected_date: date
    total_paise: int  # sum of PO line totals, computed in Python
    verdict: Verdict | None = None
    held_paise: int = 0
    at_risk_paise: int = 0
    policy_version: str | None = None
    lines_evaluated: int = 0
    lines_total: int = 0
    discrepancy_types: list[str] = Field(default_factory=list)  # derived from computed facts
    clauses: list[str] = Field(default_factory=list)  # cited policy clauses
    evidence_source: str = "none"  # "video" | "document" | "none"
    decided_at: str | None = None  # ISO timestamp of the latest stored agent decision


class CaseDetail(CaseSummary):
    delivery_id: int | None = None
    grn_number: str | None = None
    invoice_number: str | None = None
    triggered_rule_ids: list[str] = Field(default_factory=list)
    signoff_roles: list[str] = Field(default_factory=list)
    lines: list[CaseLineRead] = Field(default_factory=list)
    video_url: str | None = None
    decision: DecisionRead | None = None  # latest stored agent decision (see CASES.md §1)
    invoice_total_paise: int | None = None
