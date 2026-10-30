"""SQLAlchemy purchase-order repository. Implements domain Protocol shape."""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.infra.db.models.purchasing import PurchaseOrder


class SqlPurchaseOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_purchase_orders(self) -> list[PurchaseOrder]:
        return (
            self._session.query(PurchaseOrder)
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
