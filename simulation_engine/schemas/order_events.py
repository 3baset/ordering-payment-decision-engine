from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.base import EventBase


class OrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku_id: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)
    line_total: float = Field(gt=0)
    demand_class: Literal["A", "B", "C"] = "B"
    promotion_applied: bool = False
    discount_amount: float = 0.0

    @model_validator(mode="after")
    def validate_line_total(self) -> "OrderLine":
        expected = self.quantity * self.unit_price - self.discount_amount
        if abs(self.line_total - expected) > 0.02:
            raise ValueError(
                f"line_total {self.line_total} != quantity*unit_price - discount "
                f"({expected:.2f})"
            )
        return self


class OrderCreated(EventBase):
    event_type: Literal["OrderCreated"] = "OrderCreated"
    customer_id: str
    order_id: str
    total_value: float = Field(gt=0)
    lines: list[OrderLine] = Field(min_length=1)
    channel: Literal["rep", "app", "direct", "organic"] = "direct"
    rep_id: str | None = None
    promotion_id: str | None = None
    fraud_score: float = 0.0

    @model_validator(mode="after")
    def validate_total(self) -> "OrderCreated":
        computed = sum(line.line_total for line in self.lines)
        if abs(computed - self.total_value) > 0.02:
            raise ValueError(
                f"total_value {self.total_value} != sum of line_totals ({computed:.2f})"
            )
        return self


class OrderConfirmed(EventBase):
    event_type: Literal["OrderConfirmed"] = "OrderConfirmed"
    order_id: str
    customer_id: str


class OrderShipped(EventBase):
    event_type: Literal["OrderShipped"] = "OrderShipped"
    order_id: str
    customer_id: str


class OrderDelivered(EventBase):
    event_type: Literal["OrderDelivered"] = "OrderDelivered"
    order_id: str
    customer_id: str


class OrderCancelled(EventBase):
    event_type: Literal["OrderCancelled"] = "OrderCancelled"
    order_id: str
    customer_id: str
    reason: str = "customer_request"


class OrderReturned(EventBase):
    event_type: Literal["OrderReturned"] = "OrderReturned"
    order_id: str
    customer_id: str
    return_value: float = Field(gt=0)
    reason: str = "damaged"


class OrderRejected(EventBase):
    event_type: Literal["OrderRejected"] = "OrderRejected"
    customer_id: str
    reason: Literal["credit_limit", "churned_customer", "fraud", "other"] = "other"
    attempted_value: float = 0.0
