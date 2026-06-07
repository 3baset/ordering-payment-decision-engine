from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from schemas.base import EventBase


class CustomerCreated(EventBase):
    event_type: Literal["CustomerCreated"] = "CustomerCreated"
    segment: str
    credit_limit: float
    acquisition_channel: str
    rep_id: str | None = None
    digital_active: bool = False
    customer_type: str = ""
    area_id: str = ""
    payment_method: str = "cash"
    risk_score: float = 0.3
    name: str = ""
    phone: str = ""


class CustomerSegmentChanged(EventBase):
    event_type: Literal["CustomerSegmentChanged"] = "CustomerSegmentChanged"
    old_segment: str
    new_segment: str


class CustomerReactivated(EventBase):
    event_type: Literal["CustomerReactivated"] = "CustomerReactivated"
    days_inactive: int
    channel: str = "rep_visit"


class CustomerChurned(EventBase):
    event_type: Literal["CustomerChurned"] = "CustomerChurned"
    days_without_order: int


class CustomerBecameInactive(EventBase):
    event_type: Literal["CustomerBecameInactive"] = "CustomerBecameInactive"
    days_without_order: int


class CustomerBecameDormant(EventBase):
    event_type: Literal["CustomerBecameDormant"] = "CustomerBecameDormant"
    days_without_order: int


class CustomerAssignedToRep(EventBase):
    event_type: Literal["CustomerAssignedToRep"] = "CustomerAssignedToRep"
    rep_id: str
    previous_rep_id: str | None = None


class CreditLimitUpdated(EventBase):
    event_type: Literal["CreditLimitUpdated"] = "CreditLimitUpdated"
    old_limit: float
    new_limit: float
    reason: str = ""
