"""Read-only repository for the cases read model. Implements CaseRepository.

Every query is a SELECT; the cases view must never write a decision, so
this class deliberately has no write or commit method.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.domain.enums import RuleStatus
from app.infra.db.models.decision import Rule
from app.infra.db.models.perception import PerceptionResult
from app.infra.db.models.purchasing import (
    Delivery,
    Grn,
    GrnLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    Vendor,
)


class SqlCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_purchase_orders(self) -> list[PurchaseOrder]:
        return (
            self._session.query(PurchaseOrder)
            .options(joinedload(PurchaseOrder.lines))
            .order_by(PurchaseOrder.id)
            .all()
        )

    def get_purchase_order(self, po_id: int) -> PurchaseOrder | None:
        return (
            self._session.query(PurchaseOrder)
            .options(joinedload(PurchaseOrder.lines))
            .filter(PurchaseOrder.id == po_id)
            .first()
        )

    def get_vendor(self, vendor_id: int) -> Vendor | None:
        return self._session.get(Vendor, vendor_id)

    def get_grn_line(self, po_line_id: int) -> GrnLine | None:
        return (
            self._session.query(GrnLine)
            .filter(GrnLine.po_line_id == po_line_id)
            .order_by(GrnLine.id.desc())
            .first()
        )

    def get_invoice_line(self, po_line_id: int) -> InvoiceLine | None:
        return (
            self._session.query(InvoiceLine)
            .filter(InvoiceLine.po_line_id == po_line_id)
            .order_by(InvoiceLine.id.desc())
            .first()
        )

    def get_perception_result(self, po_line_id: int) -> PerceptionResult | None:
        """Latest perception result for the line (newest sam_run wins)."""
        return (
            self._session.query(PerceptionResult)
            .filter(PerceptionResult.po_line_id == po_line_id)
            .order_by(PerceptionResult.id.desc())
            .first()
        )

    def get_delivery_for_po(self, po_id: int) -> Delivery | None:
        return (
            self._session.query(Delivery)
            .filter(Delivery.po_id == po_id)
            .order_by(Delivery.id)
            .first()
        )

    def get_grn_for_po(self, po_id: int) -> Grn | None:
        return (
            self._session.query(Grn).filter(Grn.po_id == po_id).order_by(Grn.id).first()
        )

    def get_invoice_for_po(self, po_id: int) -> Invoice | None:
        return (
            self._session.query(Invoice)
            .filter(Invoice.po_id == po_id)
            .order_by(Invoice.id)
            .first()
        )

    def list_approved_rules(self) -> list[Rule]:
        return (
            self._session.query(Rule)
            .filter(Rule.status == RuleStatus.APPROVED.value, Rule.rule_id.isnot(None))
            .order_by(Rule.id)
            .all()
        )

    def is_duplicate_invoice(
        self, *, vendor_id: int, invoice_number: str, exclude_invoice_id: int
    ) -> bool:
        """Duplicate = second presentation: an EARLIER-booked invoice (lower
        id) with the same vendor + invoice_number already exists."""
        return (
            self._session.query(Invoice)
            .filter(
                Invoice.vendor_id == vendor_id,
                Invoice.invoice_number == invoice_number,
                Invoice.id < exclude_invoice_id,
            )
            .first()
            is not None
        )
