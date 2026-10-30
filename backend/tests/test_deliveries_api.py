"""Deliveries endpoint smoke tests: POST creates delivery+job, SSE replays
stored job_events. Pipeline runner is stubbed -- no model calls."""
from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_delivery_service, get_pipeline_runner  # noqa: E402
from app.infra.db.models import Job, PoLine, PurchaseOrder, Vendor, append_job_event  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.infra.storage import LocalFileStore  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.deliveries import DeliveryService  # noqa: E402


@pytest.fixture()
def env(tmp_path: Path) -> Iterator[tuple[TestClient, DeliveryService, int]]:
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    vendor = Vendor(code="TST", name="Test Vendor", gstin="27FAKEX1234F1Z5", city="Pune", state="MH",
                    primary_category="cartons", contact_name="A", contact_email="a@example.com")
    session.add(vendor)
    session.flush()
    po = PurchaseOrder(po_number="FM/PO/26-27/997", vendor_id=vendor.id, order_date=date(2026, 10, 1),
                       expected_date=date(2026, 10, 8), status="open", total_paise=10000, synthetic=True)
    session.add(po)
    session.flush()
    session.add(PoLine(po_id=po.id, line_no=1, category="cartons", sku="BOX-1", description="Box",
                       unit="box", qty_ordered=10, unit_price_paise=1000, tolerance_pct=5.0,
                       line_total_paise=10000))
    session.commit()
    po_id = po.id
    session.close()

    service = DeliveryService(factory, LocalFileStore(tmp_path / "storage"))
    ran: list[tuple[str, int]] = []

    async def stub_runner(job_id: str, delivery_id: int) -> dict:
        ran.append((job_id, delivery_id))
        # Simulate the pipeline writing stored events, ending in done.
        s = factory()
        try:
            job = s.get(Job, job_id)
            assert job is not None
            job.status = "done"
            append_job_event(s, job_id, "done", "done", {})
            s.commit()
        finally:
            s.close()
        return {"job_id": job_id}

    app = create_app()
    app.dependency_overrides[get_delivery_service] = lambda: service
    app.dependency_overrides[get_pipeline_runner] = lambda: stub_runner
    with TestClient(app) as client:
        yield client, service, po_id


def test_post_delivery_creates_job(env: tuple[TestClient, DeliveryService, int]) -> None:
    client, _service, po_id = env
    resp = client.post("/api/deliveries", data={"po_id": po_id},
                       files={"video": ("dock.mp4", b"fake-video-bytes", "video/mp4")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["delivery_id"] >= 1
    assert body["job_id"]


def test_post_delivery_unknown_po_404(env: tuple[TestClient, DeliveryService, int]) -> None:
    client, _service, _po_id = env
    resp = client.post("/api/deliveries", data={"po_id": 424242},
                       files={"video": ("dock.mp4", b"x", "video/mp4")})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "po_not_found"


def test_events_sse_replays_stored_events(env: tuple[TestClient, DeliveryService, int]) -> None:
    client, _service, po_id = env
    created = client.post("/api/deliveries", data={"po_id": po_id},
                          files={"video": ("dock.mp4", b"fake-video-bytes", "video/mp4")}).json()
    # Background stub has run by the time TestClient returns; stream replays.
    with client.stream("GET", f"/api/deliveries/{created['delivery_id']}/events") as resp:
        assert resp.status_code == 200
        text = "".join(chunk for chunk in resp.iter_text())
    assert "event: queued" in text
    assert "event: done" in text
    assert '"seq": 1' in text


def test_events_unknown_delivery_404(env: tuple[TestClient, DeliveryService, int]) -> None:
    client, _service, _po_id = env
    resp = client.get("/api/deliveries/424242/events")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "delivery_not_found"
