from __future__ import annotations

from typing import Literal

from pydantic import Field

from schemas.base import EventBase


class MacroStateUpdated(EventBase):
    event_type: Literal["MacroStateUpdated"] = "MacroStateUpdated"
    day_number: int = Field(ge=0)
    inflation_factor: float = Field(gt=0)
    seasonality_factor: float = Field(gt=0)
    active_promotion_count: int = Field(ge=0)


class RepVisitCompleted(EventBase):
    event_type: Literal["RepVisitCompleted"] = "RepVisitCompleted"
    rep_id: str
    customer_id: str
    outcome: Literal["no_order", "small_order", "large_order", "reactivation"]
    days_since_last_visit: int = Field(ge=0)


class AppSessionEvent(EventBase):
    event_type: Literal["AppSessionEvent"] = "AppSessionEvent"
    customer_id: str
    session_id: str
    event_subtype: Literal[
        "session_start", "screen_view", "product_search", "order_placed", "session_end"
    ] = "session_start"
    screen_name: str = ""
    search_query: str = ""
    session_duration_seconds: int = 0
    led_to_order: bool = False
