"""Policy-compiler contracts crossing services -> api. No ORM, no I/O."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Clause(BaseModel):
    clause_id: str  # e.g. "4.2"
    text: str  # verbatim clause text after the **N.N** marker


class RuleCondition(BaseModel):
    field: str
    op: str  # one of < <= > >= == between (validated in domain/rules.py)
    value: float | str | bool | list[float] | None = None


class CompiledRule(BaseModel):
    """Exactly the JSON the compiler model is asked to return for one clause.

    One threshold per rule: condition.value IS the tolerance (there is no
    separate tolerance field). A clause with per-category tolerances compiles
    to one rule per category, goods_category set to that category.
    """

    rule_id: str
    goods_category: str
    condition: RuleCondition
    action: str  # approve|partial_pay|hold|require_signoff (validated in Python)
    signoff_role: str | None = None
    source_clause: str
    source_text: str
    ambiguity: str | None = None


class CompileClauseOutput(BaseModel):
    """Wrapper: {"rules": []} means the clause yielded no checkable rule."""

    rules: list[CompiledRule] = Field(default_factory=list)


class ClauseClassification(BaseModel):
    """Step 1 of the two-step compile: what kind of clause is this?

    Only "payment_rule" clauses go to step 2 (rule compilation).
    "approval_authority" clauses become approver routes, never rules.
    """

    kind: str  # payment_rule | approval_authority | procedural | definition
    role: str | None = None  # approver role, for approval_authority
    min_value_inr: float | None = None  # approver value band lower bound (INR)
    max_value_inr: float | None = None  # approver value band upper bound (INR)


class ApproverRoute(BaseModel):
    """Who approves invoices in a value band. Routing, never a payment rule."""

    source_clause: str
    role: str
    min_value_inr: float | None = None
    max_value_inr: float | None = None


class ConflictPair(BaseModel):
    rule_id_a: str
    rule_id_b: str
    reason: str


class ConflictReport(BaseModel):
    conflicts: list[ConflictPair] = Field(default_factory=list)


class RuleFacts(BaseModel):
    """Precomputed facts a rule is evaluated against. The evaluator never
    computes counts or money itself -- callers supply them."""

    observed_count: float | None = None
    invoiced_qty: float | None = None
    po_qty: float | None = None
    grn_qty: float | None = None
    damage_count: float | None = None
    unit_price: float | None = None
    line_value: float | None = None
    goods_category: str | None = None
    variance_pct: float | None = None
    variance_vs_invoice_pct: float | None = None
    price_variance_pct: float | None = None
    invoiced_vs_po_pct: float | None = None
    duplicate_invoice: bool | None = None


class RuleOutcome(BaseModel):
    rule_id: str
    triggered: bool
    action: str | None = None  # rule action when triggered, else None
    reason: str
    field: str
    observed_value: float | str | bool | None = None


class RuleRead(BaseModel):
    """API view of one stored rule (compiled or seed-template)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: str | None = None
    goods_category: str | None = None
    condition: RuleCondition | None = None
    tolerance_pct: float | None = None
    action: str
    signoff_role: str | None = None
    source_clause: str
    source_text: str | None = None
    ambiguity: str | None = None
    status: str
    validation_errors: list[str] = Field(default_factory=list)
    conflict_with: list[str] = Field(default_factory=list)
    policy_version: str


class PolicyCompileResult(BaseModel):
    policy_version: str
    clauses_seen: int
    rules_created: int
    skipped_non_rule: int
    invalid: int
    ambiguous: int
    compiled: int = 0  # model calls made (cache misses, both compile steps)
    cache_hits: int = 0
    retries: int = 0  # clauses retried once after validation failure
    conflicts: list[ConflictPair] = Field(default_factory=list)
    approver_routes: list[ApproverRoute] = Field(default_factory=list)
    rules: list[RuleRead] = Field(default_factory=list)


# Kept for repository typing convenience; values are JSON-safe.
JsonValue = Any
