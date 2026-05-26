from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    JOURNEY_ARCHIVED = "journey.archived"
    JOURNEY_PUBLISHED = "journey.published"


class RealtimeEvent(BaseModel):
    """Generic event envelope pushed via Redis pub/sub to all WebSocket clients."""

    type: str  # EventType value or free-form string for forward compatibility
    payload: dict[str, Any] = Field(default_factory=dict)
    org_id: str | None = None  # None → broadcast to every connected client
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"use_enum_values": True}
