from fastapi import APIRouter, Depends

from app.api.deps import get_po_service
from app.domain.schemas.purchase_orders import PurchaseOrderDetail, PurchaseOrderRead
from app.services.purchase_orders import PurchaseOrderService

router = APIRouter(tags=["purchase-orders"])


@router.get("/purchase-orders", response_model=list[PurchaseOrderRead])
def list_purchase_orders(
    service: PurchaseOrderService = Depends(get_po_service),
) -> list[PurchaseOrderRead]:
    return service.list_purchase_orders()


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderDetail)
def get_purchase_order(
    po_id: int,
    service: PurchaseOrderService = Depends(get_po_service),
) -> PurchaseOrderDetail:
    return service.get_purchase_order(po_id)
