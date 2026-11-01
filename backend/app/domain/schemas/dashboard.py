"""Dashboard read contracts: Dock KPIs, analytics, eval, current policy, verify.

Shapes mirror frontend/src/types/api.ts exactly. All numbers are computed in
Python (domain/metrics.py); nothing here comes from a model.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import Verdict


class DockKpis(BaseModel):
    held_today_paise: int
    deliveries_verified: int
    deliveries_total: int
    discrepancy_rate_pct: float
    avg_time_to_verdict_s: float | None = None


class HeldByVendor(BaseModel):
    vendor_name: str
    held_paise: int
    cases: int


class TrendPoint(BaseModel):
    date: date
    deliveries: int
    discrepancies: int


class TypeMix(BaseModel):
    type: str
    count: int


class VendorRisk(BaseModel):
    vendor_name: str
    cases: int
    discrepancies: int
    held_paise: int
    risk_score: int


class AnalyticsRead(BaseModel):
    held_by_vendor: list[HeldByVendor] = Field(default_factory=list)
    trend: list[TrendPoint] = Field(default_factory=list)
    type_mix: list[TypeMix] = Field(default_factory=list)
    vendor_risk: list[VendorRisk] = Field(default_factory=list)


class VerdictMetric(BaseModel):
    label: Verdict
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    support: int


class Confusion(BaseModel):
    labels: list[Verdict]
    matrix: list[list[int]]  # rows = ground truth, columns = served verdict


class EvalCountRow(BaseModel):
    scenario: str
    category: str
    noun_phrase: str
    true_count: int
    observed_count: int
    max_visible: int
    evidence_quality: Literal["reliable", "insufficient"]
    true_damaged: int
    flagged_damaged: int
    result: Literal["PASS", "FAIL"]


class LatencyRow(BaseModel):
    model: str
    role: str
    calls: int
    p50_ms: float | None = None
    p95_ms: float | None = None


class EvalRead(BaseModel):
    verdict_metrics: list[VerdictMetric]
    confusion: Confusion
    counts: list[EvalCountRow]
    latency: list[LatencyRow]
    cases_total: int
    verdict_accuracy: float
    count_accuracy: float


class PolicyClause(BaseModel):
    clause_id: str
    section: str
    text: str


class PolicyRead(BaseModel):
    id: int
    version: str
    title: str
    document_no: str
    effective_date: str
    clauses: list[PolicyClause] = Field(default_factory=list)


class EvidenceVerifyRead(BaseModel):
    sha256: str
    verified: bool
    checked_at: datetime


class ModelCallStat(BaseModel):
    """One model_calls row reduced to what latency stats need."""

    model: str
    purpose: str
    latency_ms: int | None = None
    cache_hit: bool = False


class JobSpan(BaseModel):
    """A finished job: created_at (upload start) -> finished_at (done)."""

    started_at: datetime
    finished_at: datetime
