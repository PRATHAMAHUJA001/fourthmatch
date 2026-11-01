"""Pure rule evaluator + catalog validation. No model calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.rules import FIELD_CATALOG, evaluate_rule, evaluate_rules, validate_rule  # noqa: E402
from app.domain.schemas.policies import CompiledRule, RuleFacts  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "rules.json").read_text())


def test_field_catalog_is_exactly_the_prompt_list() -> None:
    assert set(FIELD_CATALOG) == {
        "observed_count",
        "invoiced_qty",
        "po_qty",
        "grn_qty",
        "damage_count",
        "unit_price",
        "line_value",
        "goods_category",
        "variance_pct",
        "variance_vs_invoice_pct",
        "price_variance_pct",
        "invoiced_vs_po_pct",
        "duplicate_invoice",
    }


def test_evaluate_cases_from_fixture() -> None:
    for case in FIXTURE["evaluate_cases"]:
        rule = CompiledRule.model_validate(case["rule"])
        assert validate_rule(rule) == [], case["name"]
        outcome = evaluate_rule(rule, RuleFacts.model_validate(case["facts"]))
        assert outcome.triggered is case["expected_triggered"], case["name"]
        if outcome.triggered:
            assert outcome.action == rule.action, case["name"]
        else:
            assert outcome.action is None, case["name"]


def test_invalid_rules_from_fixture() -> None:
    for case in FIXTURE["invalid_rules"]:
        rule = CompiledRule.model_validate(case["rule"])
        errors = validate_rule(rule)
        assert any(case["expected_error"] in e for e in errors), (case["name"], errors)


def test_evaluate_rules_returns_one_outcome_per_rule() -> None:
    rules = [CompiledRule.model_validate(c["rule"]) for c in FIXTURE["evaluate_cases"][:3]]
    outcomes = evaluate_rules(rules, RuleFacts(goods_category="cartons", variance_pct=5.0))
    assert [o.rule_id for o in outcomes] == [r.rule_id for r in rules]
