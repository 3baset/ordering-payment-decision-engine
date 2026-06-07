from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from schemas.base import EventBase


class InvoiceCreated(EventBase):
    event_type: Literal["InvoiceCreated"] = "InvoiceCreated"
    invoice_id: str
    order_id: str
    customer_id: str
    amount: float = Field(gt=0)
    due_date: datetime
    terms_days: int = 30


class PaymentInitiated(EventBase):
    event_type: Literal["PaymentInitiated"] = "PaymentInitiated"
    invoice_id: str
    customer_id: str
    amount: float = Field(gt=0)
    attempt_number: int = Field(ge=1)


class PaymentCaptured(EventBase):
    event_type: Literal["PaymentCaptured"] = "PaymentCaptured"
    invoice_id: str
    customer_id: str
    amount: float = Field(gt=0)
    payment_method: str = "bank_transfer"


class PaymentFailed(EventBase):
    event_type: Literal["PaymentFailed"] = "PaymentFailed"
    invoice_id: str
    customer_id: str
    amount: float = Field(gt=0)
    attempt_number: int = Field(ge=1)
    reason: str = "insufficient_funds"


class CollectionScheduled(EventBase):
    event_type: Literal["CollectionScheduled"] = "CollectionScheduled"
    invoice_id: str
    customer_id: str
    days_overdue: int = Field(ge=0)
    amount_due: float = Field(gt=0)


class CollectionPromiseMade(EventBase):
    event_type: Literal["CollectionPromiseMade"] = "CollectionPromiseMade"
    invoice_id: str
    customer_id: str
    promised_amount: float = Field(gt=0)
    promise_date: datetime


class CreditWrittenOff(EventBase):
    event_type: Literal["CreditWrittenOff"] = "CreditWrittenOff"
    invoice_id: str
    customer_id: str
    amount: float = Field(gt=0)
    days_overdue: int = Field(ge=0)
