"""STEP 2 endpoint tests: health, list POs, 404 shape. Run with pytest."""
from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_db_session  # noqa: E402
from app.infra.db.models import PoLine, PurchaseOrder, Vendor  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client_with_po(tmp_path: Path) -> Iterator[tuple[TestClient, int]]:
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    vendor = Vendor(
        code="TST", name="Test Vendor", gstin="27FAKEX1234F1Z5", city="Pune", state="MH",
        primary_category="cartons", contact_name="A", contact_email="a@example.com",
    )
    session.add(vendor)
    session.flush()
    po = PurchaseOrder(
        po_number="FM/PO/26-27/999", vendor_id=vendor.id, order_date=date(2026, 10, 1),
        expected_date=date(2026, 10, 8), status="open", total_paise=10000, synthetic=True,
    )
    session.add(po)
    session.flush()
    session.add(PoLine(
        po_id=po.id, line_no=1, category="cartons", sku="BOX-1", description="Box",
        unit="box", qty_ordered=10, unit_price_paise=1000, tolerance_pct=5.0, line_total_paise=10000,
    ))
    session.commit()
    po_id = po.id
    session.close()

    def override_session() -> Iterator[Session]:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as client:
        yield client, po_id


def test_health(client_with_po: tuple[TestClient, int]) -> None:
    client, _ = client_with_po
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_purchase_orders(client_with_po: tuple[TestClient, int]) -> None:
    client, po_id = client_with_po
    resp = client.get("/api/purchase-orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == po_id
    assert data[0]["po_number"] == "FM/PO/26-27/999"


def test_get_purchase_order_detail(client_with_po: tuple[TestClient, int]) -> None:
    client, po_id = client_with_po
    resp = client.get(f"/api/purchase-orders/{po_id}")
    assert resp.status_code == 200
    assert resp.json()["lines"][0]["qty_ordered"] == 10


def test_missing_purchase_order_404(client_with_po: tuple[TestClient, int]) -> None:
    client, _ = client_with_po
    resp = client.get("/api/purchase-orders/424242")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "po_not_found"
    assert body["error"]["message"]
    assert body["error"]["request_id"]
