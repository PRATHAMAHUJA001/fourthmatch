"""Pure-Python rule validation + evaluation. No LLM, no I/O, no arithmetic
beyond comparisons on caller-supplied facts.

FIELD_CATALOG is the single source of truth for what a compiled rule may
reference -- it mirrors the field list given to the compiler model. A rule
naming anything outside it is invalid and must never be auto-approved.
"""

from __future__ import annotations

import math

from app.domain.schemas.policies import CompiledRule, RuleFacts, RuleOutcome

# field -> "number" | "string"
FIELD_CATALOG: dict[str, str] = {
    "observed_count": "number",
    "invoiced_qty": "number",
    "po_qty": "number",
    "grn_qty": "number",
    "damage_count": "number",
    "unit_price": "number",
    "line_value": "number",
    "goods_category": "string",
    "variance_pct": "number",
    "variance_vs_invoice_pct": "number",
    "price_variance_pct": "number",
    "invoiced_vs_po_pct": "number",
    "duplicate_invoice": "bool",
}

VALID_OPS = ("<", "<=", ">", ">=", "==", "between")
VALID_ACTIONS = ("approve", "partial_pay", "hold", "require_signoff")
_WILDCARD_CATEGORIES = ("", "all", "*", "any")


def _norm_category(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def validate_rule(rule: CompiledRule) -> list[str]:
    """Return validation errors for a compiled rule; [] means valid."""
    errors: list[str] = []
    if not rule.rule_id.strip():
        errors.append("rule_id is empty")
    if not rule.source_clause.strip():
        errors.append("source_clause is empty")
    if not rule.source_text.strip():
        errors.append("source_text is empty")

    field = rule.condition.field
    op = rule.condition.op
    value = rule.condition.value
    if field not in FIELD_CATALOG:
        errors.append(f"unknown field: {field!r} (not in field catalog)")
    if op not in VALID_OPS:
        errors.append(f"unknown op: {op!r}")

    if field in FIELD_CATALOG and op in VALID_OPS:
        kind = FIELD_CATALOG[field]
        if kind == "string":
            if op != "==":
                errors.append(f"field {field!r} only supports op '==', got {op!r}")
            if not isinstance(value, str) or not value.strip():
                errors.append(f"field {field!r} needs a non-empty string value")
        elif kind == "bool":
            if op != "==":
                errors.append(f"field {field!r} only supports op '==', got {op!r}")
            if not isinstance(value, bool):
                errors.append(f"field {field!r} needs a boolean value")
        elif op == "between":
            if (
                not isinstance(value, list)
                or len(value) != 2
                or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
            ):
                errors.append("op 'between' needs value [low, high] of two numbers")
            elif float(value[0]) > float(value[1]):
                errors.append("op 'between' needs low <= high")
        else:
            if isinstance(value, bool) or not isinstance(value, int | float):
                errors.append(f"field {field!r} needs a numeric value for op {op!r}")
            elif isinstance(value, float) and not math.isfinite(value):
                errors.append(f"field {field!r} value must be finite")

    if rule.action not in VALID_ACTIONS:
        errors.append(f"unknown action: {rule.action!r}")
    if rule.action == "require_signoff" and not (rule.signoff_role or "").strip():
        errors.append("action 'require_signoff' needs a signoff_role")
    return errors


def _fact_value(facts: RuleFacts, field: str) -> float | str | bool | None:
    return getattr(facts, field, None)


def evaluate_rule(rule: CompiledRule, facts: RuleFacts) -> RuleOutcome:
    """Evaluate one rule against precomputed facts.

    Triggered means the condition holds, so the rule's action applies. One
    threshold per rule: condition.value IS the tolerance -- comparisons are
    plain, with no grace band. A missing fact never triggers -- weak
    evidence routes to a human elsewhere.
    """

    def outcome(triggered: bool, reason: str, observed: float | str | bool | None) -> RuleOutcome:
        return RuleOutcome(
            rule_id=rule.rule_id,
            triggered=triggered,
            action=rule.action if triggered else None,
            reason=reason,
            field=rule.condition.field,
            observed_value=observed,
        )

    # Category gate: a category-specific rule only applies to that category.
    rule_cat = _norm_category(rule.goods_category or "")
    if rule_cat not in _WILDCARD_CATEGORIES:
        fact_cat = _norm_category(facts.goods_category or "")
        if not fact_cat:
            return outcome(False, "missing_field:goods_category", None)
        if fact_cat != rule_cat:
            return outcome(False, "category_mismatch", facts.goods_category)

    field = rule.condition.field
    observed = _fact_value(facts, field)
    if observed is None:
        return outcome(False, f"missing_field:{field}", None)

    op = rule.condition.op
    value = rule.condition.value

    if isinstance(observed, str) or field == "goods_category":
        matched = _norm_category(str(observed)) == _norm_category(str(value))
        return outcome(matched, "match" if matched else "no_match", observed)

    if isinstance(observed, bool) or FIELD_CATALOG.get(field) == "bool":
        matched = bool(observed) == bool(value)
        return outcome(matched, "match" if matched else "no_match", observed)

    obs = float(observed)  # numeric from here on
    if op == "between":
        lo, hi = float(value[0]), float(value[1])  # type: ignore[index]
        hit = lo <= obs <= hi
    elif op == ">":
        hit = obs > float(value)  # type: ignore[arg-type]
    elif op == ">=":
        hit = obs >= float(value)  # type: ignore[arg-type]
    elif op == "<":
        hit = obs < float(value)  # type: ignore[arg-type]
    elif op == "<=":
        hit = obs <= float(value)  # type: ignore[arg-type]
    elif op == "==":
        hit = obs == float(value)  # type: ignore[arg-type]
    else:  # invalid op: validate_rule would have rejected it; never trigger
        return outcome(False, f"invalid_op:{op}", obs)
    return outcome(hit, "condition_met" if hit else "condition_not_met", obs)


def evaluate_rules(rules: list[CompiledRule], facts: RuleFacts) -> list[RuleOutcome]:
    return [evaluate_rule(rule, facts) for rule in rules]


# --- Strict checks applied ONLY to model-compiled rules (compiler service) ---
# A rule the model invented from a clause must (a) actually be about a fact
# the clause mentions, and (b) discriminate: firing on every generated
# boundary fact (tautology, e.g. line_value > 0) or on none of them
# (unsatisfiable) means it carries no policy content.

_FIELD_TEXT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "observed_count": ("observed", "received", "count"),
    "invoiced_qty": ("invoic",),
    "po_qty": ("purchase order",),
    "grn_qty": ("goods receipt", "grn"),
    "damage_count": ("damage", "damaged"),
    "unit_price": ("price",),
    "line_value": ("line value", "invoice value", "value of"),
    "goods_category": ("categor", "carton", "bagged", "steel", "material"),
    "variance_pct": ("variance", "tolerance", "shortage", "shortfall", "excess", "quantity"),
    "variance_vs_invoice_pct": ("invoic",),
    "price_variance_pct": ("price",),
    "invoiced_vs_po_pct": ("invoic",),
    "duplicate_invoice": ("duplicate",),
}

_BOUNDARY_NUMBERS = (-100.0, -5.0, -1.0, 0.0, 1.0, 2.0, 5.0, 50.0, 100.0, 1000.0, 100000.0)
_BOUNDARY_CATEGORIES = ("cartons", "bagged material", "steel coils")


def _boundary_facts(rule: CompiledRule) -> list[RuleFacts]:
    field = rule.condition.field
    rule_cat = _norm_category(rule.goods_category or "")
    fact_cat = rule.goods_category if rule_cat not in _WILDCARD_CATEGORIES else "cartons"
    if FIELD_CATALOG.get(field) == "bool":
        return [RuleFacts(goods_category=fact_cat, **{field: v}) for v in (True, False)]
    if field == "goods_category":
        return [RuleFacts(goods_category=v) for v in _BOUNDARY_CATEGORIES]
    return [RuleFacts(goods_category=fact_cat, **{field: v}) for v in _BOUNDARY_NUMBERS]  # type: ignore[arg-type]


def strict_validate_rule(rule: CompiledRule) -> list[str]:
    """validate_rule + anti-hallucination checks for model-compiled rules."""
    errors = validate_rule(rule)
    if errors:
        return errors
    field = rule.condition.field
    keywords = _FIELD_TEXT_KEYWORDS.get(field, ())
    text = rule.source_text.lower()
    if keywords and not any(k in text for k in keywords):
        errors.append(f"condition field {field!r} is not mentioned in the clause text")
    outcomes = [evaluate_rule(rule, facts).triggered for facts in _boundary_facts(rule)]
    if all(outcomes):
        errors.append("tautological condition: fires on all boundary facts")
    elif not any(outcomes):
        errors.append("unsatisfiable condition: fires on no boundary facts")
    return errors
