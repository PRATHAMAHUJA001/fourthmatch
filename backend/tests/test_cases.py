"""Cases endpoint tests: list, detail with cited clause, undecidable PO,
insufficient-evidence line, 404 shape. One smoke test per endpoint."""
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
from app.infra.db.models import (  # noqa: E402
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
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def world(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, int]]]:
    engine = make_engine(tmp_path / "cases.db")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    vendor = Vendor(
        code="TST", name="Test Vendor Ltd", gstin="27FAKEX1234F1Z5", city="Pune", state="MH",
        primary_category="cartons", contact_name="A", contact_email="a@example.com",
    )
    session.add(vendor)
    session.flush()

    def make_po(number: str, qty: int, price: int) -> tuple[PurchaseOrder, PoLine]:
        po = PurchaseOrder(
            po_number=number, vendor_id=vendor.id, order_date=date(2026, 10, 1),
            expected_date=date(2026, 10, 8), status="received",
            total_paise=qty * price, synthetic=True,
        )
        session.add(po)
        session.flush()
        line = PoLine(
            po_id=po.id, line_no=1, category="cartons", sku="CTN-550",
            description="Corrugated cartons 550 GSM", unit="box", qty_ordered=qty,
            unit_price_paise=price, tolerance_pct=0.0, line_total_paise=qty * price,
        )
        session.add(line)
        session.flush()
        return po, line

    # PO 1: short delivery on documents. PO 12, GRN 9, invoice 12 @ 55000.
    po1, line1 = make_po("FM/PO/26-27/901", 12, 55000)
    grn = Grn(grn_number="GRN-901", po_id=po1.id, received_date=date(2026, 10, 5),
              storekeeper_name="Stores", signed=True, synthetic=True)
    session.add(grn)
    session.flush()
    session.add(GrnLine(grn_id=grn.id, po_line_id=line1.id, qty_received=9, qty_damaged=0))
    inv = Invoice(invoice_number="INV-901", po_id=po1.id, vendor_id=vendor.id,
                  invoice_date=date(2026, 10, 6), due_date=date(2026, 11, 5),
                  total_paise=12 * 55000, synthetic=True)
    session.add(inv)
    session.flush()
    session.add(InvoiceLine(invoice_id=inv.id, po_line_id=line1.id, qty_invoiced=12,
                            unit_price_paise=55000, line_total_paise=12 * 55000))

    # PO 2: no GRN, no invoice line, no perception -> not decidable.
    po2, _line2 = make_po("FM/PO/26-27/902", 5, 10000)

    # PO 3: video evidence insufficient -> human_review, nothing at risk yet.
    po3, line3 = make_po("FM/PO/26-27/903", 10, 20000)
    delivery = Delivery(po_id=po3.id, status="recorded")
    session.add(delivery)
    session.flush()
    run = SamRun(delivery_id=delivery.id, video_sha256="a" * 64, seg_model="sam-3.1",
                 prompt="carton", category="cartons", status="completed")
    session.add(run)
    session.flush()
    session.add(PerceptionResult(
        delivery_id=delivery.id, po_line_id=line3.id, sam_run_id=run.id,
        category="cartons", noun_phrase="carton", observed_count=4, max_visible=4,
        per_frame_counts=[4], damaged_track_ids=[], evidence_quality="insufficient",
        reasons=["occluded"],
    ))
    inv3 = Invoice(invoice_number="INV-903", po_id=po3.id, vendor_id=vendor.id,
                   invoice_date=date(2026, 10, 6), due_date=date(2026, 11, 5),
                   total_paise=10 * 20000, synthetic=True)
    session.add(inv3)
    session.flush()
    session.add(InvoiceLine(invoice_id=inv3.id, po_line_id=line3.id, qty_invoiced=10,
                            unit_price_paise=20000, line_total_paise=10 * 20000))

    session.add(Rule(
        clause="4.2", policy_version="1.0", category="cartons",
        rule_type="quantity_variance", action="partial_pay",
        description="Quantity variance beyond tolerance.",
        rule_id="R-4.2-cartons", goods_category="cartons",
        condition_field="variance_pct", condition_op=">", condition_value=0.0,
        source_text="Quantity variance beyond tolerance holds the disputed portion.",
        status="approved", validation_errors=[], conflict_with=[],
    ))
    session.commit()
    ids = {"short": po1.id, "no_evidence": po2.id, "weak_video": po3.id}
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
        yield client, ids


def test_list_cases(world: tuple[TestClient, dict[str, int]]) -> None:
    client, ids = world
    resp = client.get("/api/cases")
    assert resp.status_code == 200
    data = {c["po_id"]: c for c in resp.json()}
    assert set(data) == set(ids.values())

    short = data[ids["short"]]
    assert short["vendor_name"] == "Test Vendor Ltd"
    assert short["verdict"] == "partial_pay"
    assert short["held_paise"] == 165000  # (12 invoiced - 9 payable) * 55000
    assert short["at_risk_paise"] == 165000
    assert short["policy_version"] == "1.0"
    assert short["lines_evaluated"] == 1

    assert data[ids["no_evidence"]]["verdict"] is None
    assert data[ids["no_evidence"]]["lines_evaluated"] == 0

    weak = data[ids["weak_video"]]
    assert weak["verdict"] == "human_review"
    assert weak["held_paise"] == 200000
    assert weak["at_risk_paise"] == 0


def test_get_case_detail_cites_clause(world: tuple[TestClient, dict[str, int]]) -> None:
    client, ids = world
    resp = client.get(f"/api/cases/{ids['short']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["grn_number"] == "GRN-901"
    assert body["invoice_number"] == "INV-901"
    assert body["triggered_rule_ids"] == ["R-4.2-cartons"]
    (line,) = body["lines"]
    assert line["po_qty"] == 12
    assert line["grn_qty"] == 9
    assert line["invoiced_qty"] == 12
    assert line["observed_count"] == 9
    assert line["evidence_source"] == "document"
    assert line["variance_pct"] == 25.0
    assert line["verdict"] == "partial_pay"
    (cited,) = line["cited_rules"]
    assert cited["rule_id"] == "R-4.2-cartons"
    assert cited["source_clause"] == "4.2"
    assert cited["source_text"]


def test_get_case_weak_evidence_line(world: tuple[TestClient, dict[str, int]]) -> None:
    client, ids = world
    body = client.get(f"/api/cases/{ids['weak_video']}").json()
    (line,) = body["lines"]
    assert line["evidence_source"] == "video"
    assert line["evidence_quality"] == "insufficient"
    assert line["verdict"] == "human_review"


def test_missing_case_404(world: tuple[TestClient, dict[str, int]]) -> None:
    client, _ = world
    resp = client.get("/api/cases/424242")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "po_not_found"
