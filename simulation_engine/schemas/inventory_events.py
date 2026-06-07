from __future__ import annotations

from typing import Literal

from pydantic import Field

from schemas.base import EventBase


class StockReceived(EventBase):
    event_type: Literal["StockReceived"] = "StockReceived"
    sku_id: str
    quantity: int = Field(gt=0)
    supplier_id: str = ""
    purchase_order_id: str = ""


class StockReserved(EventBase):
    event_type: Literal["StockReserved"] = "StockReserved"
    sku_id: str
    quantity: int = Field(gt=0)
    order_id: str


class StockReleased(EventBase):
    event_type: Literal["StockReleased"] = "StockReleased"
    sku_id: str
    quantity: int = Field(gt=0)
    order_id: str
    reason: str = "order_cancelled"


class StockoutOccurred(EventBase):
    event_type: Literal["StockoutOccurred"] = "StockoutOccurred"
    sku_id: str
    requested_quantity: int = Field(gt=0)
    available_quantity: int = Field(ge=0)
    order_id: str
    resolution: Literal["substitute", "backorder", "cancel_line"] = "cancel_line"


class PurchaseOrderCreated(EventBase):
    event_type: Literal["PurchaseOrderCreated"] = "PurchaseOrderCreated"
    sku_id: str
    quantity: int = Field(gt=0)
    supplier_id: str = ""
    expected_lead_time_days: int = Field(gt=0)


class SupplierDelay(EventBase):
    event_type: Literal["SupplierDelay"] = "SupplierDelay"
    sku_id: str
    purchase_order_id: str
    original_eta_days: int
    delay_days: int = Field(gt=0)


class BackorderFulfilled(EventBase):
    event_type: Literal["BackorderFulfilled"] = "BackorderFulfilled"
    sku_id: str
    quantity: int = Field(gt=0)
    order_id: str
