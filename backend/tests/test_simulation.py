"""Policy simulation: draft compile + re-decide all past POs. Fake model only."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_simulation_service  # noqa: E402
from app.domain.schemas.policies import ClauseClassification, CompileClauseOutput, ConflictReport  # noqa: E402
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex  # noqa: E402
from app.infra.db.models import (  # noqa: E402
    Decision,
    Delivery,
    Grn,
    GrnLine,
    Invoice,
    InvoiceLine,
    PerceptionResult,
    PoLine,
    PurchaseOrder,
    Rule,
    SamRun,
    Vendor,
)
from app.infra.db.repositories.policies import SqlRuleRepository  # noqa: E402
from app.infra.db.repositories.simulation import SqlSimulationRepository  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.policy_compiler import COMPILER_PROMPT_VERSION, PolicyCompilerService  # noqa: E402
from app.services.simulation import PolicySimulationService  # noqa: E402

BASELINE_MD = """# Baseline Policy

**Version 9.9**

**1.1** Purchase Order means an approved order.

**4.2** LENIENT quantity variance for cartons may pass.
"""

DRAFT_MD = """# Edited Policy

**Version 9.10**

**4.2** STRICT quantity variance for cartons holds payment.

**5.2** Invoiced quantity above observed quantity shall be held.

**4.9** Weight in kilograms must be checked at the dock.
"""


_SOURCE_TEXT = {
    "variance_pct": "quantity variance for cartons",
    "variance_vs_invoice_pct": "invoiced quantity above observed quantity",
    "damage_count": "damaged units are not payable",
}


def _rule(rule_id: str, field: str, value: float, tol: float | None, action: str, clause: str,
          cat: str = "all") -> dict[str, Any]:
    # tol is legacy in this helper: the threshold value IS the tolerance now.
    return {
        "rule_id": rule_id, "goods_category": cat,
        "condition": {"field": field, "op": ">", "value": value},
        "action": action, "signoff_role": None,
        "source_clause": clause, "source_text": _SOURCE_TEXT[field], "ambiguity": None,
    }


class FakeModelClient:
    """Clause text decides the rule, as a real compiler reading it would."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def call_model(self, *, purpose: str, prompt: str, output_schema: Any, **kwargs: Any) -> Any:
        self.calls.append({"purpose": purpose, "prompt": prompt, **kwargs})
        if purpose == "policy_conflicts":
            return ConflictReport.model_validate({"conflicts": []})
        clause_id = prompt.split(":", 1)[0].replace("Clause", "").strip()
        if purpose == "policy_classify":
            kind = "definition" if clause_id == "1.1" else "payment_rule"
            return ClauseClassification.model_validate({"kind": kind})
        if clause_id == "4.9":
            rule = _rule("R-WEIGHT", "damage_count", 0.0, None, "hold", "4.9")
            rule["condition"] = {"field": "weight_kg", "op": ">", "value": 1.0}
            rule["source_text"] = "Weight in kilograms must be checked at the dock."
            rule["ambiguity"] = "needs weight_kg, not in field list"
            return CompileClauseOutput.model_validate({"rules": [rule]})
        if clause_id == "5.2":
            return CompileClauseOutput.model_validate(
                {"rules": [_rule("R-INV-OVER", "variance_vs_invoice_pct", 0.0, 0.0, "hold", "5.2")]})
        if "LENIENT" in prompt:
            return CompileClauseOutput.model_validate(
                {"rules": [_rule("R-QTY", "variance_pct", 5.0, 5.0, "hold", "4.2", cat="cartons")]})
        return CompileClauseOutput.model_validate(
            {"rules": [_rule("R-QTY", "variance_pct", 0.0, 0.0, "hold", "4.2", cat="cartons")]})


def _world(tmp_path: Path) -> tuple[PolicySimulationService, PolicyCompilerService, Any]:
    engine = make_engine(tmp_path / "sim.db")
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    fake = FakeModelClient()
    compiler = PolicyCompilerService(SqlRuleRepository(session), fake, "cfg-compiler")  # type: ignore[arg-type]
    sim = PolicySimulationService(SqlSimulationRepository(session), compiler)

    vendor = Vendor(code="VND-T", name="Test Vendor", gstin="27FAKET0000T1Z5", city="Pune",
                    state="Maharashtra", primary_category="cartons", contact_name="T",
                    contact_email="t@example.in")
    session.add(vendor)
    session.flush()

    def make_po(number: str, category: str, qty: int, price: int, *, grn_qty: int | None,
                inv_qty: int, damaged: int = 0, video_observed: int | None = None) -> PurchaseOrder:
        po = PurchaseOrder(po_number=number, vendor_id=vendor.id, order_date=date(2026, 4, 1),
                           expected_date=date(2026, 4, 5), status="received", total_paise=qty * price,
                           synthetic=True)
        session.add(po)
        session.flush()
        line = PoLine(po_id=po.id, line_no=1, category=category, sku="SKU-1", description="item",
                      unit="box", qty_ordered=qty, unit_price_paise=price, tolerance_pct=0.0,
                      line_total_paise=qty * price)
        session.add(line)
        session.flush()
        grn = Grn(grn_number=f"GRN-{number}", po_id=po.id, received_date=date(2026, 4, 3),
                  storekeeper_name="T", signed=True, synthetic=True)
        session.add(grn)
        session.flush()
        if grn_qty is not None:
            session.add(GrnLine(grn_id=grn.id, po_line_id=line.id, qty_received=grn_qty,
                                qty_damaged=damaged))
        inv = Invoice(invoice_number=f"INV-{number}", po_id=po.id, vendor_id=vendor.id,
                      invoice_date=date(2026, 4, 4), due_date=date(2026, 5, 4),
                      total_paise=inv_qty * price, synthetic=True)
        session.add(inv)
        session.flush()
        session.add(InvoiceLine(invoice_id=inv.id, po_line_id=line.id, qty_invoiced=inv_qty,
                                unit_price_paise=price, line_total_paise=inv_qty * price))
        if video_observed is not None:
            delivery = Delivery(po_id=po.id, grn_id=grn.id, status="recorded")
            session.add(delivery)
            session.flush()
            run = SamRun(delivery_id=delivery.id, video_sha256="a" * 64, seg_model="cfg-seg",
                         prompt="carton", category=category, status="completed")
            session.add(run)
            session.flush()
            session.add(PerceptionResult(
                delivery_id=delivery.id, po_line_id=line.id, sam_run_id=run.id,
                category=category, noun_phrase="carton", observed_count=video_observed,
                max_visible=video_observed, per_frame_counts=[], damaged_track_ids=[],
                evidence_quality="reliable", reasons=[]))
        session.flush()
        return po

    # Video PO: 97/100 observed. Lenient baseline (tol 5) approves; strict draft holds.
    po_video = make_po("PO-VIDEO", "cartons", 100, 100_00, grn_qty=100, inv_qty=100, video_observed=97)
    # Document PO: invoiced 112 vs GRN-observed 100. Baseline has no such rule; draft 5.2 holds.
    make_po("PO-DOC", "bagged_material", 100, 50_00, grn_qty=100, inv_qty=112)
    # Skipped PO: no GRN line, no perception -> no observed quantity exists.
    make_po("PO-SKIP", "cartons", 10, 100_00, grn_qty=None, inv_qty=10)
    # Stale stored decision on the video PO: baseline recomputes approve/₹0.
    session.add(Decision(po_id=po_video.id, verdict="approve", reason="stale",
                         amount_at_risk_paise=999, decided_by="agent"))
    session.commit()
    return sim, compiler, session


def _approve_baseline(compiler: PolicyCompilerService) -> None:
    result = asyncio.run(compiler.compile_policy(BASELINE_MD))
    assert result.rules_created == 1
    compiler.approve_rule(result.rules[0].id)


def test_simulate_diff_drift_totals_and_non_mutation(tmp_path: Path) -> None:
    sim, compiler, session = _world(tmp_path)
    _approve_baseline(compiler)
    rules_before = session.query(Rule).count()
    decisions_before = session.query(Decision).count()

    result = asyncio.run(sim.simulate(policy_version="9.9", markdown=DRAFT_MD))

    assert result.baseline_approved_rules == 1
    assert result.draft_invalid == 1  # weight_kg rule reported, never evaluated
    assert {d.rule.rule_id for d in result.draft_rules} == {"R-QTY", "R-INV-OVER", "R-WEIGHT"}
    assert result.pos_evaluated == 2 and result.lines_skipped == 1
    assert result.unchanged_count == 0
    by_po = {c.po_number: c for c in result.changed}
    assert set(by_po) == {"PO-VIDEO", "PO-DOC"}
    assert by_po["PO-VIDEO"].before_verdict.value == "approve"
    assert by_po["PO-VIDEO"].after_verdict.value == "hold"
    assert by_po["PO-VIDEO"].after_held_paise == 100 * 100_00
    assert by_po["PO-VIDEO"].lines[0].evidence_source == "video"
    assert by_po["PO-DOC"].lines[0].evidence_source == "document"
    assert by_po["PO-DOC"].after_held_paise == 112 * 50_00

    assert result.totals.held_before_paise == 0
    assert result.totals.held_after_paise == 100 * 100_00 + 112 * 50_00
    assert result.totals.held_after_inr == "₹15,600"
    by_source = {t.evidence_source: t for t in result.totals_by_evidence_source}
    assert by_source["video"].held_after_paise == 100 * 100_00
    assert by_source["document"].held_after_paise == 112 * 50_00

    assert len(result.drift) == 1
    assert result.drift[0].po_number == "PO-VIDEO"
    assert result.drift[0].stored_amount_at_risk_paise == 999
    assert result.drift[0].baseline_held_paise == 0

    # Non-mutation: no rule or decision row was added, changed, or approved.
    assert session.query(Rule).count() == rules_before
    assert session.query(Decision).count() == decisions_before
    assert {r.rule_id for r in compiler.list_rules()} == {"R-QTY"}
    assert compiler.list_rules(status="approved")[0].rule_id == "R-QTY"
    session.close()


def test_simulate_unknown_version_404s(tmp_path: Path) -> None:
    sim, compiler, session = _world(tmp_path)
    _approve_baseline(compiler)
    with pytest.raises(Exception) as exc:
        asyncio.run(sim.simulate(policy_version="0.0", markdown=DRAFT_MD))
    assert exc.value.code == "policy_not_found"  # type: ignore[attr-defined]
    session.close()


def test_compile_draft_cache_counts(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "draft.db")
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    cache = Sha256Cache(tmp_path / "cache")
    compiler = PolicyCompilerService(  # type: ignore[arg-type]
        SqlRuleRepository(session), FakeModelClient(), "cfg-compiler", cache=cache)
    # Pre-seed both per-clause cache entries (classify + compile) for 4.2 STRICT.
    from app.services.policy_compiler import split_clauses

    clause = split_clauses(DRAFT_MD)[0]
    digest = sha256_hex(clause.text.encode())
    cache.put_json(cache_key_for("policy_classify", COMPILER_PROMPT_VERSION,
                                 "cfg-compiler", digest), {"kind": "payment_rule"})
    cache.put_json(cache_key_for("policy_compile", COMPILER_PROMPT_VERSION,
                                 "cfg-compiler", digest), {"rules": []})
    draft = asyncio.run(compiler.compile_draft(DRAFT_MD))
    assert draft.cache_hits == 2
    # 2 classify + 2 compile misses on the other clauses, plus 1 retry for
    # the invalid 4.9 rule (retry returns the same invalid rule in the fake).
    assert draft.compiled == 5
    assert draft.retries == 1
    session.close()


@pytest.fixture()
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    sim, compiler, session = _world(tmp_path)
    _approve_baseline(compiler)
    app = create_app()
    app.dependency_overrides[get_simulation_service] = lambda: sim
    with TestClient(app) as client:
        yield client
    session.close()


def test_api_simulate(api_client: TestClient) -> None:
    resp = api_client.post("/api/policies/9.9/simulate", json={"policy_text": DRAFT_MD})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["policy_version"] == "9.9" and body["draft_policy_version"] == "9.10"
    assert len(body["changed"]) == 2 and len(body["drift"]) == 1
    assert body["totals"]["held_after_inr"] == "₹15,600"
    assert api_client.post("/api/policies/0.0/simulate", json={"policy_text": DRAFT_MD}).status_code == 404
    assert api_client.post("/api/policies/9.9/simulate", json={"policy_text": ""}).status_code == 422
