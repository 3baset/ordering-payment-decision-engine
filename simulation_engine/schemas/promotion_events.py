from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from schemas.base import EventBase


class PromotionCreated(EventBase):
    event_type: Literal["PromotionCreated"] = "PromotionCreated"
    promotion_id: str
    promotion_type: Literal["percentage", "fixed", "bogo"] = "percentage"
    value: float = Field(gt=0)
    target_segments: list[str] = Field(default_factory=list)
    target_skus: list[str] = Field(default_factory=list)
    start_date: datetime
    end_date: datetime
    budget: float = 0.0


class PromotionActivated(EventBase):
    event_type: Literal["PromotionActivated"] = "PromotionActivated"
    promotion_id: str


class PromotionApplied(EventBase):
    event_type: Literal["PromotionApplied"] = "PromotionApplied"
    promotion_id: str
    order_id: str
    customer_id: str
    discount_amount: float = Field(gt=0)
    original_value: float = Field(gt=0)


class PromotionExpired(EventBase):
    event_type: Literal["PromotionExpired"] = "PromotionExpired"
    promotion_id: str
    total_redemptions: int = 0
    total_discount_given: float = 0.0
