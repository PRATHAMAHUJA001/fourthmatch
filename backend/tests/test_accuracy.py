"""Decision + compiler accuracy over all 12 seeded cases. Findings, not gates.

Two reported scores, both against data/ground_truth.json (via a freshly
seeded tmp DB, so inputs come from real PO/GRN/invoice rows):
  (a) DECISION accuracy  -- domain/decision.py + REFERENCE_RULES below
  (b) COMPILER accuracy  -- domain/decision.py + rules the model actually
      compiled from the committed policy, read ONLY from the compiler cache
      (populate it with scripts/compile_policy_cache.py; the test skips,
      loudly, if the cache is incomplete -- it never calls a model)

A case is correct only if verdict AND held_paise both match the answer key.
Every mismatch is printed with the triggered rule ids. Mismatches are
findings to show, never tuned away; seed/expected.py and ground_truth.json
are not edited to make these numbers move.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.decision import decide_delivery  # noqa: E402
from app.domain.money import format_inr  # noqa: E402
from app.domain.rules import validate_rule  # noqa: E402
from app.domain.schemas.policies import CompileClauseOutput, CompiledRule  # noqa: E402
from app.domain.schemas.simulation import LineDecisionInput  # noqa: E402
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex  # noqa: E402
from app.infra.db.models import GrnLine, Invoice, InvoiceLine, PurchaseOrder  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.seed.generate import seed  # noqa: E402
from app.services.policy_compiler import (  # noqa: E402
    COMPILER_PROMPT_VERSION,
    clause_rule_errors,
    retry_cache_key,
    split_clauses,
)

MANIFEST_PATH = ROOT / "samples" / "scenarios" / "manifest.json"
POLICY_PATH = ROOT / "data" / "policy" / "receiving_policy.md"


def _mk(rule_id: str, clause: str, field: str, op: str, value: object,
        action: str, cat: str = "all") -> CompiledRule:
    # One threshold per rule: value IS the tolerance.
    return CompiledRule(
        rule_id=rule_id, goods_category=cat,
        condition={"field": field, "op": op, "value": value},  # type: ignore[arg-type]
        action=action,
        signoff_role="Stores Manager" if action == "require_signoff" else None,
        source_clause=clause, source_text=clause, ambiguity=None,
    )


# Reference rules: the policy clauses as intended, hand-written once.
# 4.2 quantity tolerance (category-specific), 5.1 price, 5.2 invoiced>PO,
# 5.3 duplicate, 6.1 damage. Actions follow the payable-quantity rule:
# shortage/damage/over-invoice dispute only a portion -> partial_pay.
REFERENCE_RULES = [
    _mk("REF-4.2-cartons", "4.2", "variance_pct", ">", 0.0, "partial_pay", "cartons"),
    _mk("REF-4.2-bagged", "4.2", "variance_pct", ">", 2.0, "partial_pay", "bagged_material"),
    _mk("REF-4.2-steel", "4.2", "variance_pct", ">", 0.0, "partial_pay", "steel_coils"),
    _mk("REF-5.1", "5.1", "price_variance_pct", ">", 2.0, "hold"),
    _mk("REF-5.2", "5.2", "invoiced_vs_po_pct", ">", 0.0, "partial_pay"),
    _mk("REF-5.3", "5.3", "duplicate_invoice", "==", True, "hold"),
    _mk("REF-6.1", "6.1", "damage_count", ">", 0.0, "partial_pay"),
]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict:
    tmp = tmp_path_factory.mktemp("accuracy")
    truth_path = tmp / "ground_truth.json"
    seed(db_path=tmp / "accuracy.db", manifest_path=MANIFEST_PATH,
         policy_path=POLICY_PATH, truth_path=truth_path)
    session = make_session_factory(make_engine(tmp / "accuracy.db"))()
    truth = json.loads(truth_path.read_text())
    yield {"session": session, "truth": truth}
    session.close()


def _case_inputs(world: dict) -> dict[str, list[LineDecisionInput]]:
    session = world["session"]
    out: dict[str, list[LineDecisionInput]] = {}
    for case in world["truth"]["scenarios_and_discrepancies"]:
        po = session.query(PurchaseOrder).filter_by(po_number=case["po_number"]).one()
        is_video = case["source"] == "video"
        lines: list[LineDecisionInput] = []
        for i, po_line in enumerate(sorted(po.lines, key=lambda ln: ln.line_no)):
            grn = session.query(GrnLine).filter_by(po_line_id=po_line.id).one()
            inv_line = session.query(InvoiceLine).filter_by(po_line_id=po_line.id).one()
            invoice = session.get(Invoice, inv_line.invoice_id)
            duplicate = (
                session.query(Invoice)
                .filter(Invoice.vendor_id == invoice.vendor_id,
                        Invoice.invoice_number == invoice.invoice_number,
                        Invoice.id < invoice.id)  # earlier-booked only
                .first() is not None
            )
            truth = case["truth"][i] if case["truth"] else None
            observed = truth["qty"] if (is_video and truth) else grn.qty_received
            damaged = truth["damaged"] if (is_video and truth) else grn.qty_damaged
            lines.append(LineDecisionInput(
                po_line_id=po_line.id, goods_category=po_line.category,
                evidence_source="video" if is_video else "document",
                evidence_quality="reliable" if is_video else None,
                observed_count=observed, invoiced_qty=inv_line.qty_invoiced,
                po_qty=po_line.qty_ordered, grn_qty=grn.qty_received, damage_count=damaged,
                unit_price_paise=inv_line.unit_price_paise,
                po_unit_price_paise=po_line.unit_price_paise,
                duplicate_invoice=duplicate,
                line_value_paise=inv_line.qty_invoiced * inv_line.unit_price_paise,
            ))
        out[case["po_number"]] = lines
    return out


def _score(world: dict, inputs: dict, rules: list[CompiledRule]) -> tuple[int, list[str], tuple[int, int]]:
    """Correct iff verdict AND at_risk_paise match the key. Held is reported
    separately -- it is cash withheld, not value at risk."""
    correct, mismatches = 0, []
    total_held = total_at_risk = 0
    for case in world["truth"]["scenarios_and_discrepancies"]:
        got = decide_delivery(inputs[case["po_number"]], rules)
        total_held += got.held_paise
        total_at_risk += got.at_risk_paise
        ok = got.verdict.value == case["correct_verdict"] and got.at_risk_paise == case["amount_at_risk_paise"]
        if ok:
            correct += 1
        else:
            mismatches.append(
                f"{case['po_number']} ({case.get('scenario_id') or case.get('seeded_type')}): "
                f"decision={got.verdict.value} held={format_inr(got.held_paise)} "
                f"at_risk={format_inr(got.at_risk_paise)} "
                f"triggered={got.triggered_rule_ids} vs ground_truth={case['correct_verdict']} "
                f"at_risk={case['amount_at_risk_inr']}"
            )
    return correct, mismatches, (total_held, total_at_risk)


def test_decision_accuracy_reference_rules(world: dict, capsys: pytest.CaptureFixture[str]) -> None:
    inputs = _case_inputs(world)
    correct, mismatches, (held, at_risk) = _score(world, inputs, REFERENCE_RULES)
    total = len(world["truth"]["scenarios_and_discrepancies"])
    with capsys.disabled():
        print(f"\nDECISION ACCURACY (reference rules) {correct}/{total} "
              f"[verdict + at_risk; total held={format_inr(held)} total at_risk={format_inr(at_risk)}]")
        for m in mismatches:
            print(f"MISMATCH {m}")
    assert total == 12


def _compiled_rules_from_cache() -> list[CompiledRule] | None:
    """Two-step cache: classify entry decides whether a compile entry exists."""
    from app.domain.schemas.policies import ClauseClassification

    settings = get_settings()
    cache = Sha256Cache(settings.cache_root)
    clauses = split_clauses(POLICY_PATH.read_text())
    rules: list[CompiledRule] = []
    seen: set[str] = set()
    for clause in clauses:
        key = cache_key_for("policy_compile", COMPILER_PROMPT_VERSION,
                            settings.compiler_model, sha256_hex(clause.text.encode()))
        raw = cache.get_json(key)
        if raw is None:
            cls_key = cache_key_for("policy_classify", COMPILER_PROMPT_VERSION,
                                    settings.compiler_model, sha256_hex(clause.text.encode()))
            cls_raw = cache.get_json(cls_key)
            if cls_raw is None:
                return None
            if ClauseClassification.model_validate(cls_raw).kind != "payment_rule":
                continue
            return None
        first_rules = CompileClauseOutput.model_validate(raw).rules
        # Mirror the service's one validator-feedback retry: if the cached
        # first attempt failed validation, prefer its cached retry entry.
        flat_errors = [e for errs in clause_rule_errors(clause, first_rules) for e in errs]
        if flat_errors:
            retry_raw = cache.get_json(
                retry_cache_key(settings.compiler_model, clause, first_rules, flat_errors))
            if retry_raw is not None:
                retried = CompileClauseOutput.model_validate(retry_raw).rules
                if retried:
                    first_rules = retried
        for rule in first_rules:
            if rule.source_clause != clause.clause_id:
                continue
            if rule.rule_id in seen:
                rule = rule.model_copy(update={"rule_id": f"{rule.rule_id}#{clause.clause_id}"})
            seen.add(rule.rule_id)
            if not validate_rule(rule):
                rules.append(rule)
    return rules


def _rule_metrics(compiled: list[CompiledRule]) -> tuple[list[str], list[str], list[str]]:
    """matched / missing / extra of compiled rules vs REFERENCE_RULES.

    A compiled rule matches a reference rule on (source_clause, field,
    action, normalized goods_category).
    """
    from app.domain.rules import _norm_category

    def key(r: CompiledRule) -> tuple[str, str, str, str]:
        cat = _norm_category(r.goods_category)
        cat = "" if cat in ("", "all", "*", "any") else cat  # wildcard equivalence
        return (r.source_clause, r.condition.field, r.action, cat)

    ref_by_key = {key(r): r for r in REFERENCE_RULES}
    comp_by_key = {key(r): r for r in compiled}
    matched = [f"{ref_by_key[k].rule_id}<->{comp_by_key[k].rule_id}"
               for k in sorted(ref_by_key.keys() & comp_by_key.keys())]
    missing = [ref_by_key[k].rule_id for k in sorted(ref_by_key.keys() - comp_by_key.keys())]
    extra = [comp_by_key[k].rule_id for k in sorted(comp_by_key.keys() - ref_by_key.keys())]
    return matched, missing, extra


def test_duplicate_is_earlier_booked_only(world: dict) -> None:
    """Clause 5.3: only the SECOND presentation is a duplicate. The original
    invoice (scn1_clean) must not flag; the duplicate case must."""
    from app.infra.db.repositories.simulation import SqlSimulationRepository

    session = world["session"]
    repo = SqlSimulationRepository(session)
    dup_case = next(c for c in world["truth"]["scenarios_and_discrepancies"]
                    if "duplicate" in (c.get("seeded_type") or ""))
    clean_po = next(c for c in world["truth"]["scenarios_and_discrepancies"]
                    if c.get("scenario_id") == "scn1_clean")

    def is_dup(po_number: str) -> bool:
        po = session.query(PurchaseOrder).filter_by(po_number=po_number).one()
        inv_line = session.query(InvoiceLine).filter_by(po_line_id=po.lines[0].id).one()
        invoice = session.get(Invoice, inv_line.invoice_id)
        return repo.is_duplicate_invoice(
            vendor_id=invoice.vendor_id, invoice_number=invoice.invoice_number,
            exclude_invoice_id=invoice.id)

    assert is_dup(dup_case["po_number"]) is True
    assert is_dup(clean_po["po_number"]) is False


def test_compiler_accuracy_compiled_rules(world: dict, capsys: pytest.CaptureFixture[str]) -> None:
    rules = _compiled_rules_from_cache()
    if rules is None:
        pytest.skip("compiler cache incomplete for committed policy -- "
                    "run: PYTHONPATH=backend backend/.venv/bin/python scripts/compile_policy_cache.py")
    inputs = _case_inputs(world)
    correct, mismatches, (held, at_risk) = _score(world, inputs, rules)
    total = len(world["truth"]["scenarios_and_discrepancies"])
    matched, missing, extra = _rule_metrics(rules)
    with capsys.disabled():
        print(f"\nCOMPILER ACCURACY (model-compiled rules) {correct}/{total} "
              f"using {len(rules)} valid compiled rules "
              f"[total held={format_inr(held)} total at_risk={format_inr(at_risk)}]")
        for r in rules:
            print(f"COMPILED {r.rule_id} clause={r.source_clause} {r.condition.field}"
                  f"{r.condition.op}{r.condition.value} "
                  f"action={r.action} cat={r.goods_category}")
        print(f"RULE METRICS matched={matched}")
        print(f"RULE METRICS missing={missing}")
        print(f"RULE METRICS extra={extra}")
        for m in mismatches:
            print(f"MISMATCH {m}")
    assert total == 12
