"""Seed tests: manifest is source of truth, ground truth is derived independently,
policy numbers match the template, seeding is idempotent/upserting, and the
expected-verdict module is independent of the runtime decision path.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import date
from pathlib import Path
from random import Random

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.schemas.seed import EvalLine, ManifestFile  # noqa: E402
from app.infra.db.models import Decision, Delivery, Grn, Invoice, Job, PurchaseOrder, Vendor  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.seed.cases import VENDORS  # noqa: E402
from app.seed.expected import expected_verdict  # noqa: E402
from app.seed.generate import build_po_data, seed  # noqa: E402
from app.seed.manifest import load_manifest  # noqa: E402
from app.seed.policy_template import POLICY, check_policy  # noqa: E402

MANIFEST_PATH = ROOT / "samples" / "scenarios" / "manifest.json"
POLICY_PATH = ROOT / "data" / "policy" / "receiving_policy.md"
APP = ROOT / "backend" / "app"


def _seed(tmp: Path) -> dict:
    return {
        "db_path": tmp / "test.db",
        "manifest_path": MANIFEST_PATH,
        "policy_path": tmp / "receiving_policy.md",
        "truth_path": tmp / "ground_truth.json",
    }


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory):
    tmp = tmp_path_factory.mktemp("seed")
    kwargs = _seed(tmp)
    (tmp / "receiving_policy.md").write_text(POLICY_PATH.read_text())
    result = seed(**kwargs)
    manifest = load_manifest(MANIFEST_PATH, repo_root=ROOT)
    truth_doc = json.loads(kwargs["truth_path"].read_text())
    session = make_session_factory(make_engine(kwargs["db_path"]))()
    yield {"kwargs": kwargs, "tmp": tmp, "result": result, "manifest": manifest,
           "truth_doc": truth_doc, "session": session}
    session.close()


def _fresh_policy(tmp: Path) -> Path:
    policy = tmp / "receiving_policy.md"
    policy.write_text(POLICY_PATH.read_text())
    return policy


def test_manifest_pos_match_manifest(seeded) -> None:
    s = seeded["session"]
    assert s.query(Delivery).count() == len(seeded["manifest"])
    for scn in seeded["manifest"]:
        po = s.query(PurchaseOrder).filter_by(scenario_id=scn.scenario_id).one()
        assert [line.qty_ordered for line in po.lines] == [line.po_qty for line in scn.lines]
        grn = s.query(Grn).filter_by(po_id=po.id).one()
        assert [line.qty_received for line in grn.lines] == [line.grn_qty for line in scn.lines]
        invoice = s.query(Invoice).filter_by(po_id=po.id).one()
        assert [line.qty_invoiced for line in invoice.lines] == [line.invoice_qty for line in scn.lines]
        delivery = s.query(Delivery).filter_by(scenario_id=scn.scenario_id).one()
        assert delivery.video_path == scn.video_path
        assert (ROOT / delivery.video_path).exists()


def test_manifest_schema_aliases_match_file_exactly() -> None:
    raw = json.loads(MANIFEST_PATH.read_text())
    doc = ManifestFile.model_validate_json(MANIFEST_PATH.read_text())
    dumped = doc.model_dump(by_alias=True)
    assert dumped["scenarios"][0]["id"] == raw["scenarios"][0]["id"]
    assert set(dumped["scenarios"][0]["lines"][0]) == {"category", "po", "grn", "invoice", "true_count", "true_damaged"}
    bad = json.loads(MANIFEST_PATH.read_text())
    bad["scenarios"][0]["lines"][0]["po_qty"] = bad["scenarios"][0]["lines"][0]["po"]
    with pytest.raises(ValidationError):
        ManifestFile.model_validate(bad)


def test_ground_truth_has_12_cases_derived_from_manifest_and_tolerances(seeded) -> None:
    entries = seeded["truth_doc"]["scenarios_and_discrepancies"]
    assert len(entries) == 12
    assert len([e for e in entries if e["scenario_id"]]) == len(seeded["manifest"])
    assert len([e for e in entries if not e["scenario_id"]]) == 8
    by_scn = {e["scenario_id"]: e for e in entries if e["scenario_id"]}
    for scn in seeded["manifest"]:
        e = by_scn[scn.scenario_id]
        assert [t["qty"] for t in e["truth"]] == [line.truth_qty for line in scn.lines]
        assert [t["damaged"] for t in e["truth"]] == [line.truth_damaged for line in scn.lines]
    s = seeded["session"]
    for e in entries:  # every verdict recomputes standalone from template tolerances
        po = s.query(PurchaseOrder).filter_by(po_number=e["po_number"]).one()
        grn = s.query(Grn).filter_by(po_id=po.id).one()
        invoice = s.query(Invoice).filter_by(po_id=po.id).one()
        truth_by_line = e["truth"] or [None] * len(po.lines)
        lines = []
        for po_line, grn_line, inv_line, truth in zip(
                po.lines, grn.lines, invoice.lines, truth_by_line, strict=True):
            assert po_line.tolerance_pct == POLICY["quantity_tolerance_pct"][po_line.category]
            lines.append(EvalLine(
                category=po_line.category, po_qty=po_line.qty_ordered,
                grn_qty=grn_line.qty_received, grn_damaged=grn_line.qty_damaged,
                inv_qty=inv_line.qty_invoiced, po_price_paise=po_line.unit_price_paise,
                inv_price_paise=inv_line.unit_price_paise,
                truth_qty=truth["qty"] if truth else None,
                truth_damaged=truth["damaged"] if truth else 0))
        recomputed = expected_verdict(
            lines, duplicate="duplicate_invoice_number" in e["discrepancy_types"])
        assert e["correct_verdict"] == recomputed.verdict, e["po_number"]
        assert e["policy_clauses"] == recomputed.policy_clauses, e["po_number"]
        assert e["amount_at_risk_paise"] == recomputed.amount_at_risk_paise, e["po_number"]
        assert e["requires_debit_note"] == recomputed.requires_debit_note, e["po_number"]


def test_video_scenarios_by_hand(seeded) -> None:
    """Hand-asserted expected outcomes for the 4 video scenarios (point 4)."""
    by_scn = {e["scenario_id"]: e for e in seeded["truth_doc"]["scenarios_and_discrepancies"]
              if e["scenario_id"]}
    assert by_scn["scn1_clean"]["correct_verdict"] == "approve"
    assert by_scn["scn2_short"]["correct_verdict"] in {"hold", "partial_pay"}
    assert by_scn["scn3_damage"]["correct_verdict"] == "partial_pay"
    assert by_scn["scn3_damage"]["requires_debit_note"] is True
    assert by_scn["scn4_mixed"]["correct_verdict"] == "partial_pay"


def test_policy_numbers_match_template(seeded) -> None:
    text = seeded["kwargs"]["policy_path"].read_text()
    check = check_policy(text)
    assert check.ok, f"mismatched={check.mismatched} missing={check.missing} header_ok={check.header_ok}"
    tampered = text.replace("2.0% for bagged material", "9.0% for bagged material")
    assert tampered != text
    bad = check_policy(tampered)
    assert "4.2" in bad.mismatched


def test_seed_loader_verifies_and_refuses_policy(tmp_path: Path) -> None:
    kwargs = _seed(tmp_path)
    kwargs["policy_path"].write_text(
        POLICY_PATH.read_text().replace("2.0% for bagged material", "9.0% for bagged material"))
    before = kwargs["policy_path"].read_bytes()
    with pytest.raises(RuntimeError, match="does not match policy_template"):
        seed(**kwargs)
    assert kwargs["policy_path"].read_bytes() == before  # loader never rewrites


def test_build_po_data_deterministic_random42(seeded) -> None:
    first = build_po_data(seeded["manifest"], Random(42))
    second = build_po_data(seeded["manifest"], Random(42))
    assert [p.model_dump() for p in first] == [p.model_dump() for p in second]
    assert len(first) == 30


def test_seed_is_idempotent_upsert(seeded) -> None:
    kwargs = seeded["kwargs"]
    policy_bytes = kwargs["policy_path"].read_bytes()
    truth_bytes = kwargs["truth_path"].read_bytes()
    counts_before = {m.__tablename__: seeded["session"].query(m).count()
                     for m in (PurchaseOrder, Grn, Invoice, Delivery)}
    second = seed(**kwargs)
    assert second.policy_verified is True
    assert second.truth_changed is False
    assert kwargs["policy_path"].read_bytes() == policy_bytes
    assert kwargs["truth_path"].read_bytes() == truth_bytes
    assert counts_before == {m.__tablename__: seeded["session"].query(m).count()
                             for m in (PurchaseOrder, Grn, Invoice, Delivery)}


def test_seed_prunes_stale_seeded_rows_but_never_runtime(tmp_path: Path) -> None:
    kwargs = _seed(tmp_path)
    _fresh_policy(tmp_path)
    seed(**kwargs)
    session = make_session_factory(make_engine(kwargs["db_path"]))()
    try:
        stale_vendor = Vendor(code="VND-999", name="Stale Vendor", gstin="27FAKEZ9999A1Z5",
                              city="Pune", state="Maharashtra", primary_category="cartons",
                              contact_name="Stale", contact_email="stale@example.in", synthetic=True)
        session.add(stale_vendor)
        session.flush()
        stale_po = PurchaseOrder(po_number="FM/PO/26-27/999", vendor_id=stale_vendor.id,
                                 order_date=date(2026, 1, 1), expected_date=date(2026, 1, 8),
                                 total_paise=100, synthetic=True)
        session.add(stale_po)
        session.flush()
        runtime_po = PurchaseOrder(po_number="FM/PO/26-27/998", vendor_id=stale_vendor.id,
                                   order_date=date(2026, 1, 1), expected_date=date(2026, 1, 8),
                                   total_paise=100, synthetic=True)
        session.add(runtime_po)
        session.flush()
        session.add(Decision(po_id=runtime_po.id, verdict="hold", reason="runtime"))
        session.commit()
    finally:
        session.close()

    seed(**kwargs)  # stale plain PO+vendor pruned; runtime-linked PO kept
    session = make_session_factory(make_engine(kwargs["db_path"]))()
    try:
        numbers = {po.po_number for po in session.query(PurchaseOrder).all()}
        assert "FM/PO/26-27/999" not in numbers
        assert "FM/PO/26-27/998" in numbers  # has a Decision: runtime, never touched
        assert session.query(Decision).count() == 1
        assert {v.gstin for v in session.query(Vendor).all()} >= {v.gstin for v in VENDORS}
    finally:
        session.close()


def test_seed_reset_wipes_whole_db(tmp_path: Path) -> None:
    kwargs = _seed(tmp_path)
    _fresh_policy(tmp_path)
    seed(**kwargs)
    session = make_session_factory(make_engine(kwargs["db_path"]))()
    session.add(Job(kind="perception", status="queued"))
    session.commit()
    session.close()

    seed(**kwargs)  # plain reseed keeps runtime rows
    session = make_session_factory(make_engine(kwargs["db_path"]))()
    assert session.query(Job).count() == 1
    session.close()

    seed(**kwargs, reset=True)  # dev-only wipe
    session = make_session_factory(make_engine(kwargs["db_path"]))()
    try:
        assert session.query(Job).count() == 0
        assert session.query(PurchaseOrder).count() == 30
    finally:
        session.close()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_expected_verdict_import_directions() -> None:
    expected_imports = _imports(APP / "seed" / "expected.py")
    forbidden_for_expected = {"app.domain.rules", "app.seed.verdict"}
    assert not (expected_imports & forbidden_for_expected), expected_imports
    assert not any(m == "app.services" or m.startswith("app.services.") for m in expected_imports)
    # Nothing under services/ or domain/ (rules included, present or future)
    # may import the seed's ground-truth module in any form.
    for base in (APP / "services", APP / "domain"):
        for path in base.rglob("*.py"):
            imports = _imports(path)
            bad = {m for m in imports
                   if m == "app.seed" or m.startswith("app.seed.") or m.endswith("seed.expected")}
            assert not bad, f"{path} imports ground-truth seed module: {bad}"
