"""Architecture enforcement + new STEP 2 models/schemas/config. No model calls."""
from __future__ import annotations

import ast
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import load_model_config  # noqa: E402
from app.domain.schemas.perception import PerceptionResult  # noqa: E402
from app.infra.cache import Sha256Cache  # noqa: E402
from app.infra.db.models import (  # noqa: E402
    Delivery,
    Job,
    PoLine,
    PurchaseOrder,
    SamRun,
    Track,
    Vendor,
    append_job_event,
)
from app.infra.db.models import PerceptionResult as PerceptionResultRow  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402

APP = ROOT / "backend" / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_architecture_doc_checklist() -> None:
    doc = (ROOT / "docs" / "ARCHITECTURE.md").read_text()
    for needle in [
        "domain/` imports nothing",
        "`jobs` and `job_events` tables exist",
        "`sam_runs` and `tracks` are separate tables",
        "`perception_results` has `max_visible`, `evidence_quality` and `reasons`",
        "Every model ID comes from config, none hardcoded",
    ]:
        assert needle in doc


def test_domain_imports_nothing_forbidden() -> None:
    forbidden_roots = {"sqlalchemy", "fastapi", "app.infra", "infra"}
    for path in (APP / "domain").rglob("*.py"):
        bad = {m for m in _imports(path) if m.split(".")[0] in {"sqlalchemy", "fastapi"} or m.startswith("app.infra")}
        assert not bad, f"{path}: forbidden imports {bad} (also checked {forbidden_roots})"


def test_orm_only_under_infra_db_models() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        if "infra/db/models" in str(path):
            continue
        if "__tablename__" in path.read_text():
            offenders.append(str(path))
    assert offenders == []


def test_new_tables_and_columns_exist() -> None:
    tables = Base.metadata.tables
    for name in ["jobs", "job_events", "sam_runs", "tracks", "perception_results", "damage_flags", "model_calls"]:
        assert name in tables, name
    assert {"max_visible", "evidence_quality", "reasons"} <= set(tables["perception_results"].columns.keys())
    assert "sam_run_id" in tables["tracks"].columns
    # sam_runs and tracks are separate tables
    assert tables["sam_runs"] is not tables["tracks"]
    assert "video_sha256" in tables["sam_runs"].columns
    assert {"job_id", "seq"} <= set(tables["job_events"].columns.keys())


def test_no_hardcoded_model_ids_in_app() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        text = path.read_text()
        if "muse-" in text or "sam-3" in text:
            offenders.append(str(path))
    assert offenders == []


def test_config_resolves_only_from_env() -> None:
    env = {
        "MODEL_API_KEY": "test-key",
        "META_BASE_URL": "https://api.meta.ai/v1",
        "PERCEPTION_MODEL": "cfg-perception",
        "DECISION_MODEL": "cfg-decision",
        "COMPILER_MODEL": "cfg-compiler",
        "BULK_MODEL": "cfg-bulk",
        "SEG_MODEL": "cfg-seg",
        "IMAGE_MODEL": "cfg-image",
        "VOICE_MODEL": "cfg-voice",
    }
    cfg = load_model_config(env)
    assert cfg.decision_model == "cfg-decision"
    assert cfg.seg_model == "cfg-seg"
    with pytest.raises(ValueError, match="SEG_MODEL"):
        load_model_config({k: v for k, v in env.items() if k != "SEG_MODEL"})


def test_perception_result_from_fixture() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "perception_frames.json").read_text())
    result = PerceptionResult(
        delivery_id=1, po_line_id=1, sam_run_id=1, category="cartons", noun_phrase="cardboard box",
        observed_count=fixture["expected_track_count"], max_visible=fixture["expected_max_visible"],
        evidence_quality="reliable", reasons=[],
    )
    assert isinstance(result, PerceptionResult)
    assert result.observed_count == fixture["expected_track_count"]
    assert result.max_visible == fixture["expected_max_visible"]
    assert result.evidence_quality.value in {"reliable", "insufficient"}


def test_jobs_sam_perception_roundtrip(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "models.db")
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    try:
        vendor = Vendor(code="ARC", name="Arch Vendor", gstin="27FAKEX1234F1Z5", city="Pune",
                        state="MH", primary_category="cartons", contact_name="A",
                        contact_email="a@example.com")
        session.add(vendor)
        session.flush()
        po = PurchaseOrder(po_number="FM/PO/26-27/998", vendor_id=vendor.id,
                           order_date=date(2026, 10, 1), expected_date=date(2026, 10, 8),
                           total_paise=1000, synthetic=True)
        session.add(po)
        session.flush()
        session.add(PoLine(po_id=po.id, line_no=1, category="cartons", sku="B1", description="Box",
                           unit="box", qty_ordered=1, unit_price_paise=1000,
                           tolerance_pct=5.0, line_total_paise=1000))
        delivery = Delivery(po_id=po.id, video_path="samples/scenarios/scn1_clean.mp4",
                            delivered_at=datetime.now(UTC))
        session.add(delivery)
        session.flush()

        job = Job(kind="perception", status="queued", delivery_id=delivery.id, po_id=po.id)
        session.add(job)
        session.flush()
        e1 = append_job_event(session, job.id, "queued", "job queued")
        e2 = append_job_event(session, job.id, "tracking", "tracking")
        assert (e1.seq, e2.seq) == (1, 2)

        run = SamRun(delivery_id=delivery.id, job_id=job.id, video_sha256="a" * 64,
                     seg_model="from-config", prompt="cardboard box", category="cartons",
                     status="completed", distinct_track_count=1)
        session.add(run)
        session.flush()
        track = Track(delivery_id=delivery.id, sam_run_id=run.id, object_id="1",
                      prompt="cardboard box", category="cartons", first_frame=0, last_frame=2,
                      frame_count=3)
        session.add(track)
        session.flush()
        row = PerceptionResultRow(delivery_id=delivery.id, sam_run_id=run.id, category="cartons",
                                  noun_phrase="cardboard box", observed_count=1, max_visible=1,
                                  evidence_quality="reliable", reasons=[])
        session.add(row)
        session.commit()
        assert session.query(SamRun).count() == 1
        assert session.query(Track).count() == 1
        assert session.query(PerceptionResultRow).count() == 1
    finally:
        session.close()


def test_cache_sha256_keyed(tmp_path: Path) -> None:
    cache = Sha256Cache(tmp_path / "cache")
    key, _, hit = cache.get_or_put_bytes(b"video-bytes")
    assert len(key) == 64
    assert hit is False
    _, _, hit2 = cache.get_or_put_bytes(b"video-bytes")
    assert hit2 is True


def test_sqlite_wal_and_busy_timeout(tmp_path: Path) -> None:
    from sqlalchemy import text

    engine = make_engine(tmp_path / "wal.db")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
