from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, use_enum_values=True)

    event_id:       UUID     = Field(default_factory=uuid4)
    event_type:     str
    aggregate_id:   str
    timestamp:      datetime
    causation_id:   UUID | None = None
    correlation_id: UUID | None = None
