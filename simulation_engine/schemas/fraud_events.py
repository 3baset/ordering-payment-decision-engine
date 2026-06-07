from __future__ import annotations

from typing import Literal

from pydantic import Field

from schemas.base import EventBase


class FraudAlertEvent(EventBase):
    event_type: Literal["FraudAlertEvent"] = "FraudAlertEvent"
    customer_id: str
    order_id: str | None = None
    fraud_type: Literal[
        "velocity", "amount_spike", "identity", "return_abuse", "payment"
    ] = "velocity"
    fraud_score: float = Field(ge=0.0, le=1.0)
    action_taken: Literal["flagged", "rejected", "suspended"] = "flagged"
    details: str = ""
