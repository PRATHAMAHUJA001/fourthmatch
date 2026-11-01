"""Read-only repository for policy simulation. Implements SimulationRepository.

Every query is a SELECT; simulation must never touch saved decisions or
rules, so this class deliberately has no write or commit method.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.infra.db.models.decision import Decision, Rule
from app.infra.db.models.perception import PerceptionResult
from app.infra.db.models.purchasing import Delivery, GrnLine, Invoice, InvoiceLine, PurchaseOrder


class SqlSimulationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_rules_for_version(self, policy_version: str, status: str | None = None) -> list[Rule]:
        query = self._session.query(Rule).filter(Rule.policy_version == policy_version)
        if status is not None:
            query = query.filter(Rule.status == status)
        return query.order_by(Rule.id).all()

    def list_purchase_orders(self) -> list[PurchaseOrder]:
        return self._session.query(PurchaseOrder).order_by(PurchaseOrder.id).all()

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

    def get_latest_decision(self, po_id: int) -> Decision | None:
        return (
            self._session.query(Decision)
            .filter(Decision.po_id == po_id)
            .order_by(Decision.id.desc())
            .first()
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
