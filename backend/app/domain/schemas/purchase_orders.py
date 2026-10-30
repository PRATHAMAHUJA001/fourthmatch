"""Purchase-order contracts crossing services -> api."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class PoLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_no: int
    category: str
    sku: str
    description: str
    unit: str
    qty_ordered: int
    unit_price_paise: int
    tolerance_pct: float
    line_total_paise: int


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    po_number: str
    vendor_id: int
    order_date: date
    expected_date: date
    status: str
    currency: str
    total_paise: int
    scenario_id: str | None = None
    synthetic: bool = True


class PurchaseOrderDetail(PurchaseOrderRead):
    lines: list[PoLineRead] = []


class HealthRead(BaseModel):
    status: str = "ok"

