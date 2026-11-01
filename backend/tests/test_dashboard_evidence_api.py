"""Smoke tests for the dashboard + evidence endpoints, one per endpoint, on a
freshly seeded tmp DB with approved reference rules and perception rows taken
from data/eval_counts.json. No model calls; ffmpeg is used for frame grabs."""
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_app_settings, get_db_session  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.domain.policy_doc import parse_policy  # noqa: E402
from app.infra.db.models import (  # noqa: E402
    Decision,
    Delivery,
    Job,
    ModelCall,
    PerceptionResult,
    PurchaseOrder,
    Rule,
    SamRun,
)
from app.infra.db.repositories.evidence import SqlEvidenceRepository  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.infra.storage import LocalFileStore  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed.generate import seed  # noqa: E402
from app.services.evidence import latest_pack_for_po  # noqa: E402
from app.services.policy_docs import PolicyDocService  # noqa: E402

POLICY_PATH = ROOT / "data" / "policy" / "receiving_policy.md"
MANIFEST_PATH = ROOT / "samples" / "scenarios" / "manifest.json"
EVAL_COUNTS = json.loads((ROOT / "data" / "eval_counts.json").read_text())
GROUND_TRUTH = json.loads((ROOT / "data" / "ground_truth.json").read_text())["scenarios_and_discrepancies"]

REFERENCE_RULES = [  # (rule_id, clause, field, op, value, action, category)
    ("R-4.2-cartons", "4.2", "variance_pct", ">", 0.0, "partial_pay", "cartons"),
    ("R-4.2-bagged", "4.2", "variance_pct", ">", 2.0, "partial_pay", "bagged_material"),
    ("R-4.2-steel", "4.2", "variance_pct", ">", 0.0, "partial_pay", "steel_coils"),
    ("R-5.1", "5.1", "price_variance_pct", ">", 2.0, "hold", "all"),
    ("R-5.2", "5.2", "invoiced_vs_po_pct", ">", 0.0, "partial_pay", "all"),
    ("R-5.3", "5.3", "duplicate_invoice", "==", True, "hold", "all"),
    ("R-6.1", "6.1", "damage_count", ">", 0.0, "partial_pay", "all"),
]


def _delivery_id_for(session: Session, scenario_id: str) -> int:
    return session.query(Delivery).filter(Delivery.scenario_id == scenario_id).one().id


@pytest.fixture()
def world(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session], Path]]:
    db_path = tmp_path / "world.db"
    seed(db_path=db_path, manifest_path=MANIFEST_PATH, policy_path=POLICY_PATH, truth_path=tmp_path / "gt.json")
    factory = make_session_factory(make_engine(db_path))
    session = factory()
    clause_text = {c.clause_id: c.text for c in parse_policy(POLICY_PATH.read_text()).clauses}
    for rule in session.query(Rule).all():
        session.delete(rule)
    for rule_id, clause, field, op, value, action, cat in REFERENCE_RULES:
        session.add(Rule(
            clause=clause, policy_version="1.0", category=None if cat == "all" else cat,
            rule_type=f"compiled:{field}", action=action, description="reference", rule_id=rule_id,
            goods_category=cat, condition_field=field, condition_op=op, condition_value=value,
            source_text=clause_text[clause], status="approved", validation_errors=[], conflict_with=[],
        ))
    session.flush()
    for delivery in session.query(Delivery).all():
        run = SamRun(delivery_id=delivery.id, video_sha256=f"{delivery.id:064d}", seg_model="cfg-seg",
                     prompt="p", category="cartons", status="completed", proxy_fps=2.0)
        session.add(run)
        session.flush()
        for line in session.get(PurchaseOrder, delivery.po_id).lines:  # type: ignore[union-attr]
            ev = next(c for c in EVAL_COUNTS
                      if c["scenario"] == delivery.scenario_id and c["category"].replace(" ", "_") == line.category)
            session.add(PerceptionResult(
                delivery_id=delivery.id, po_line_id=line.id, sam_run_id=run.id, category=line.category,
                noun_phrase=ev["noun_phrase"], observed_count=ev["observed_count"], max_visible=ev["max_visible"],
                damaged_track_ids=ev["damaged_track_ids"], evidence_quality=ev["evidence_quality"], reasons=[],
            ))
    now = datetime.now(UTC)
    session.add(Decision(po_id=2, delivery_id=2, verdict="partial_pay", reason="Video shows fewer boxes than the GRN.",
                         policy_clauses=["4.2"], amount_at_risk_paise=110000, created_at=now - timedelta(days=1)))
    for sec in (30, 50):
        session.add(Job(kind="perception", status="done", delivery_id=1, po_id=1,
                        created_at=now - timedelta(hours=1), finished_at=now - timedelta(hours=1) + timedelta(seconds=sec)))
    session.add(Job(kind="perception", status="failed", delivery_id=1, po_id=1, created_at=now))
    for latency in (100, 300):
        session.add(ModelCall(purpose="understanding", model="cfg-perception", latency_ms=latency, status="ok"))
    session.commit()
    session.close()

    def override_session() -> Iterator[Session]:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    storage = tmp_path / "storage"
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_app_settings] = lambda: Settings(storage_root=storage)
    with TestClient(app) as client:
        yield client, factory, storage


def _scenario(factory: sessionmaker[Session], scenario_id: str) -> int:
    with factory() as s:
        return _delivery_id_for(s, scenario_id)


# ------------------------------------------------------------- dashboard
def test_dock_kpis_smoke(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, _, _ = world
    body = client.get("/api/dock/kpis").json()
    assert set(body) == {"held_today_paise", "deliveries_verified", "deliveries_total",
                         "discrepancy_rate_pct", "avg_time_to_verdict_s"}
    cases = client.get("/api/cases").json()
    decided = [c for c in cases if c["verdict"]]
    assert body["deliveries_total"] == len(decided) == 30
    assert body["deliveries_verified"] == sum(1 for c in decided if c["verdict"] == "approve")
    assert body["held_today_paise"] == sum(c["held_paise"] for c in decided)
    assert body["discrepancy_rate_pct"] == round((len(decided) - body["deliveries_verified"]) / len(decided) * 100, 1)
    assert body["avg_time_to_verdict_s"] == 40.0  # (30 + 50) / 2; the failed job is ignored


def test_dock_kpis_null_time_without_finished_jobs(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, factory, _ = world
    with factory() as s:
        s.query(Job).delete()
        s.commit()
    assert client.get("/api/dock/kpis").json()["avg_time_to_verdict_s"] is None


def test_analytics_smoke(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, _, _ = world
    body = client.get("/api/analytics").json()
    assert set(body) == {"held_by_vendor", "trend", "type_mix", "vendor_risk"}
    assert len(body["trend"]) == 30
    assert sum(p["deliveries"] for p in body["trend"]) <= 30
    assert all(p["discrepancies"] <= p["deliveries"] for p in body["trend"])
    cases = client.get("/api/cases").json()
    assert sum(v["held_paise"] for v in body["held_by_vendor"]) == sum(c["held_paise"] for c in cases)
    assert sum(v["cases"] for v in body["vendor_risk"]) == 30
    types = {t["type"] for t in body["type_mix"]}
    assert {"short_shipment_beyond_tolerance", "invoice_price_above_po", "duplicate_invoice_number"} <= types
    assert "grn_contradicted_by_video" in types


def test_eval_smoke(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, _, _ = world
    body = client.get("/api/eval").json()
    assert body["cases_total"] == len(GROUND_TRUTH)
    assert body["confusion"]["labels"] == ["approve", "partial_pay", "hold", "human_review"]
    matrix = body["confusion"]["matrix"]
    assert sum(map(sum, matrix)) == len(GROUND_TRUTH)
    assert body["verdict_accuracy"] == 1.0  # reference rules reproduce the answer key
    assert all(matrix[i][i] == sum(matrix[i]) for i in range(4))
    by_label = {m["label"]: m for m in body["verdict_metrics"]}
    assert by_label["human_review"]["precision"] is None and by_label["human_review"]["f1"] is None
    assert by_label["partial_pay"]["support"] == sum(1 for c in GROUND_TRUTH if c["correct_verdict"] == "partial_pay")
    assert len(body["counts"]) == len(EVAL_COUNTS)
    assert body["count_accuracy"] == sum(c["result"] == "PASS" for c in EVAL_COUNTS) / len(EVAL_COUNTS)
    latency = body["latency"]
    assert latency == [{"model": "cfg-perception", "role": "understanding", "calls": 2, "p50_ms": 200.0, "p95_ms": 290.0}]


def test_policies_current_default_and_latest_upload(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, _, storage = world
    default = client.get("/api/policies/current")
    assert default.status_code == 200
    body = default.json()
    assert (body["id"], body["version"], body["document_no"], body["effective_date"]) == (1, "1.0", "FM-POL-PROC-001", "2026-04-01")
    assert {"clause_id": "4.2", "section": "Quantity verification"} == {
        k: next(c for c in body["clauses"] if c["clause_id"] == "4.2")[k] for k in ("clause_id", "section")}
    PolicyDocService(LocalFileStore(storage), POLICY_PATH).save_uploaded("# Draft Policy\n**Version 9.9**\n## 1 Part\n**1.1** Only clause.\n", "9.9")
    latest = client.get("/api/policies/current").json()
    assert latest["version"] == "9.9" and latest["id"] == 2 and latest["title"] == "Draft Policy"
    assert [c["clause_id"] for c in latest["clauses"]] == ["1.1"]


# -------------------------------------------------------------- evidence
def test_build_pack_pdf_json_and_verify(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, factory, storage = world
    delivery_id = _scenario(factory, "scn2_short")
    built = client.post(f"/api/deliveries/{delivery_id}/evidence-pack")
    assert built.status_code == 201
    pack = built.json()
    assert pack["verified"] is True
    assert pack["files"] == ["evidence_pack.json", "evidence_pack.pdf", "debit_note.pdf"]
    assert len(pack["sha256"]) == 64

    pdf = client.get(f"/api/deliveries/{delivery_id}/evidence-pack")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    raw = client.get(f"/api/deliveries/{delivery_id}/evidence-pack", params={"format": "json"})
    assert raw.status_code == 200
    assert hashlib.sha256(raw.content).hexdigest() == pack["sha256"]  # exact bytes are the hash input
    doc = json.loads(raw.content)
    assert doc["synthetic"] is True and doc["verdict"] == "partial_pay"
    assert doc["amount_held_display"] == "₹1,100"
    row = doc["four_match"][0]
    assert (row["po_qty"], row["grn_qty"], row["invoiced_qty"], row["vision_count"]) == (14, 14, 14, 12)
    assert row["contradicts_grn"] is True
    clause = doc["cited_clauses"][0]
    assert clause["clause_id"] == "4.2" and clause["clause_source"] == "policy_document"
    assert clause["clause_text"].startswith("The quantity tolerance for acceptance")
    assert 3 <= len(doc["frames"]) <= 6
    assert doc["agent_trace"]["recorded"] is True
    assert doc["debit_note"]["total_paise"] == 110000

    verify = client.get(f"/api/evidence/{pack['sha256']}/verify")
    assert verify.status_code == 200
    assert verify.json()["verified"] is True and verify.json()["sha256"] == pack["sha256"]
    assert verify.json()["checked_at"]

    with factory() as s:
        latest = latest_pack_for_po(SqlEvidenceRepository(s), 2)
    assert latest is not None and latest.sha256 == pack["sha256"] and latest.verified is True
    assert [p.name for p in (storage / "evidence" / "po_2" / pack["sha256"][:16]).iterdir()] != []


def test_verify_detects_tampering(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, factory, storage = world
    delivery_id = _scenario(factory, "scn3_damage")
    sha = client.post(f"/api/deliveries/{delivery_id}/evidence-pack").json()["sha256"]
    pdf_path = storage / "evidence" / "po_3" / sha[:16] / "evidence_pack.pdf"
    pdf_path.write_bytes(pdf_path.read_bytes() + b"\n%tampered")
    verify = client.get(f"/api/evidence/{sha}/verify").json()
    assert verify["verified"] is False
    with factory() as s:
        pack = latest_pack_for_po(SqlEvidenceRepository(s), 3)
    assert pack is not None and pack.verified is False


def test_debit_note_only_for_partial_pay(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, factory, _ = world
    partial = client.get(f"/api/deliveries/{_scenario(factory, 'scn4_mixed')}/debit-note")
    assert partial.status_code == 200 and partial.content.startswith(b"%PDF")
    assert "debit-note_" in partial.headers["content-disposition"]
    clean = client.get(f"/api/deliveries/{_scenario(factory, 'scn1_clean')}/debit-note")
    assert clean.status_code == 404
    assert clean.json()["error"]["code"] == "debit_note_not_applicable"


def test_evidence_errors(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, _, _ = world
    assert client.post("/api/deliveries/9999/evidence-pack").status_code == 404
    assert client.get("/api/deliveries/9999/evidence-pack").json()["error"]["code"] == "delivery_not_found"
    assert client.get("/api/deliveries/9999/debit-note").status_code == 404
    assert client.get(f"/api/evidence/{'a' * 64}/verify").status_code == 404
    assert client.get("/api/evidence/not-a-hash/verify").status_code == 422
    assert client.get("/api/deliveries/1/evidence-pack", params={"format": "xml"}).status_code == 422


def test_rebuild_keeps_history_and_latest_wins(world: tuple[TestClient, sessionmaker[Session], Path]) -> None:
    client, factory, _ = world
    delivery_id = _scenario(factory, "scn2_short")
    first = client.post(f"/api/deliveries/{delivery_id}/evidence-pack").json()
    second = client.post(f"/api/deliveries/{delivery_id}/evidence-pack").json()
    assert first["sha256"] != second["sha256"]  # generated_at is part of the hashed JSON
    assert client.get(f"/api/evidence/{first['sha256']}/verify").json()["verified"] is True
    raw = client.get(f"/api/deliveries/{delivery_id}/evidence-pack", params={"format": "json"}).content
    assert hashlib.sha256(raw).hexdigest() == second["sha256"]
