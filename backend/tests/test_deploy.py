"""Deployment pieces: SPA fallback, demo upload gate, offline demo loader. No model calls."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_app_settings, get_delivery_service, get_pipeline_runner  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.domain.schemas.jobs import DeliveryCreated  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed.demo import load_demo  # noqa: E402

INDEX = "<!doctype html><title>FourthMatch SPA</title>"


@pytest.fixture()
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text(INDEX)
    (d / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside dist")
    return d


def test_spa_serves_index_assets_and_client_routes(dist: Path) -> None:
    client = TestClient(create_app(Settings(frontend_dist=dist)))
    assert client.get("/").text == INDEX
    assert client.get("/cases/1").text == INDEX
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/health").status_code == 200


def test_api_404_stays_json_not_index(dist: Path) -> None:
    client = TestClient(create_app(Settings(frontend_dist=dist)))
    for path in ("/api/nope", "/api"):
        resp = client.get(path)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "endpoint_not_found"


def test_missing_asset_is_404_not_index(dist: Path) -> None:
    client = TestClient(create_app(Settings(frontend_dist=dist)))
    assert client.get("/assets/gone.js").status_code == 404


def test_spa_does_not_escape_dist(dist: Path) -> None:
    client = TestClient(create_app(Settings(frontend_dist=dist)))
    resp = client.get("/%2e%2e/secret.txt")
    assert "outside dist" not in resp.text


def test_no_dist_means_api_only(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(frontend_dist=tmp_path / "missing")))
    assert client.get("/cases/1").status_code == 404


class _StubService:
    def create_delivery(self, **_kwargs: object) -> DeliveryCreated:
        return DeliveryCreated(delivery_id=1, job_id="job-1")


def _demo_client(settings: Settings) -> TestClient:
    async def runner(_job_id: str, _delivery_id: int) -> dict:
        return {}

    app = create_app(settings)
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_delivery_service] = lambda: _StubService()
    app.dependency_overrides[get_pipeline_runner] = lambda: runner
    return TestClient(app)


def _upload(client: TestClient, passcode: str | None = None):  # noqa: ANN202
    headers = {"X-Demo-Passcode": passcode} if passcode is not None else {}
    return client.post("/api/deliveries", data={"po_id": 1}, headers=headers,
                       files={"video": ("d.mp4", b"x", "video/mp4")})


def test_demo_upload_requires_passcode(tmp_path: Path) -> None:
    client = _demo_client(Settings(demo_mode=True, demo_passcode="open-sesame", frontend_dist=tmp_path))
    for bad in (None, "", "wrong"):
        resp = _upload(client, bad)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "demo_passcode_required"
    assert _upload(client, "open-sesame").status_code == 201


def test_demo_upload_disabled_without_server_passcode(tmp_path: Path) -> None:
    client = _demo_client(Settings(demo_mode=True, demo_passcode="", frontend_dist=tmp_path))
    resp = _upload(client, "")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "live_uploads_disabled"


def test_demo_upload_rate_limited_after_limit(tmp_path: Path) -> None:
    client = _demo_client(Settings(demo_mode=True, demo_passcode="pw", live_upload_limit_per_hour=2,
                                   frontend_dist=tmp_path))
    assert _upload(client, "pw").status_code == 201
    assert _upload(client, "pw").status_code == 201
    resp = _upload(client, "pw")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "upload_rate_limited"
    assert _upload(client, "wrong").status_code == 403  # bad passcode never burns/reveals quota


def test_non_demo_mode_needs_no_passcode(tmp_path: Path) -> None:
    client = _demo_client(Settings(demo_mode=False, frontend_dist=tmp_path))
    assert _upload(client).status_code == 201


def _counts(db: Path) -> dict[str, int]:
    conn = sqlite3.connect(db)
    try:
        return {t: conn.execute(f"select count(*) from {t}").fetchone()[0]
                for t in ("purchase_orders", "deliveries", "sam_runs", "perception_results", "tracks", "rules")}
    finally:
        conn.close()


def test_demo_loader_is_idempotent_and_reads_committed_files(tmp_path: Path) -> None:
    db = tmp_path / "demo.db"
    # Test-only rule set standing in for an exported snapshot (the real one is produced
    # on the machine that ran the policy compile: scripts/export_demo_snapshot.py).
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({
        "policy_version": "test",
        "rules": [{"rule_id": "T-4.2", "goods_category": "all",
                   "condition": {"field": "variance_pct", "op": ">", "value": 0.0},
                   "action": "partial_pay", "signoff_role": None, "source_clause": "4.2",
                   "source_text": "t", "ambiguity": None}],
        "tracks": [{"scenario": "scn1_clean", "category": "cartons", "object_id": "0",
                    "first_frame": 0, "last_frame": 5, "frame_count": 6, "confidence": 0.9}],
    }))
    args = dict(
        db_path=db, manifest_path=ROOT / "samples" / "scenarios" / "manifest.json",
        policy_path=ROOT / "data" / "policy" / "receiving_policy.md",
        truth_path=tmp_path / "ground_truth.json", settings=Settings(storage_root=tmp_path / "s"),
        snapshot_path=snapshot,
    )
    first = load_demo(**args)  # type: ignore[arg-type]
    after_first = _counts(db)
    second = load_demo(**args)  # type: ignore[arg-type]
    assert _counts(db) == after_first
    eval_rows = [r for r in json.loads((ROOT / "data" / "eval_counts.json").read_text())
                 if r.get("observed_count") is not None]
    assert first.perception_rows == len(eval_rows) == after_first["perception_results"]
    assert second.perception_rows == 0 and second.perception_skipped_existing == len(eval_rows)
    assert after_first["rules"] >= 1 and first.rules_loaded == 1 and first.rules_source.endswith("snapshot.json")
    assert after_first["tracks"] == 1


def test_demo_loader_warns_when_no_rules_available(tmp_path: Path) -> None:
    report = load_demo(
        tmp_path / "d.db", ROOT / "samples" / "scenarios" / "manifest.json",
        ROOT / "data" / "policy" / "receiving_policy.md", tmp_path / "gt.json",
        Settings(storage_root=tmp_path / "s"), snapshot_path=tmp_path / "absent.json",
    )
    assert report.rules_loaded == 0
    assert any("NO APPROVED RULES" in w for w in report.warnings)


def test_demo_mode_gates_every_write_route(tmp_path) -> None:
    """In DEMO_MODE no model-calling or state-changing route works without the passcode."""
    from fastapi.testclient import TestClient

    from app.api.deps import get_app_settings
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(
        DEMO_MODE=True, DEMO_PASSCODE="pw",
        DATABASE_URL=f"sqlite:///{tmp_path / 'g.db'}", FRONTEND_DIST=tmp_path / "nodist",
    )
    app = create_app(settings)
    app.dependency_overrides[get_app_settings] = lambda: settings
    with TestClient(app) as client:
        for path in (
            "/api/policies", "/api/policies/1/simulate", "/api/rules/1/approve",
            "/api/rules/1/reject", "/api/deliveries/1/decide", "/api/deliveries/1/evidence-pack",
        ):
            r = client.post(path)
            assert r.status_code == 403, (path, r.status_code, r.text)
            assert r.json()["error"]["code"] == "demo_passcode_required"
