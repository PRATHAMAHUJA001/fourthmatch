"""Purchase-order use cases. Returns domain schemas only."""
from __future__ import annotations

from app.core.errors import NotFoundError
from app.domain.protocols import PurchaseOrderRepository
from app.domain.schemas.purchase_orders import PurchaseOrderDetail, PurchaseOrderRead


class PurchaseOrderService:
    def __init__(self, repository: PurchaseOrderRepository) -> None:
        self._repository = repository

    def list_purchase_orders(self) -> list[PurchaseOrderRead]:
        return [PurchaseOrderRead.model_validate(po) for po in self._repository.list_purchase_orders()]

    def get_purchase_order(self, po_id: int) -> PurchaseOrderDetail:
        po = self._repository.get_purchase_order(po_id)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} was not found.", code="po_not_found")
        return PurchaseOrderDetail.model_validate(po)
