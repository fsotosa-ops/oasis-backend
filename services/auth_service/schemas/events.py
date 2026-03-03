from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import UUID4, BaseModel, Field


class EventStatus(StrEnum):
    upcoming = "upcoming"
    live = "live"
    past = "past"
    cancelled = "cancelled"


class LandingConfig(BaseModel):
    title: Optional[str] = None
    welcome_message: Optional[str] = None
    primary_color: str = "#3B82F6"
    background_color: str = "#0F172A"
    show_qr: bool = True
    custom_logo_url: Optional[str] = None


class EventCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus = EventStatus.upcoming
    journey_id: Optional[UUID4] = None
    landing_config: LandingConfig = Field(default_factory=LandingConfig)


class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[EventStatus] = None
    journey_id: Optional[UUID4] = None
    landing_config: Optional[LandingConfig] = None
    is_active: Optional[bool] = None


class EventResponse(BaseModel):
    id: str
    organization_id: str
    journey_id: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus
    landing_config: LandingConfig
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PublicEventResponse(BaseModel):
    """Endpoint público — no expone IDs internos sensibles innecesariamente."""
    id: str
    name: str
    slug: str
    org_id: str
    org_slug: str
    org_name: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus
    landing_config: LandingConfig
    journey_id: Optional[str] = None
