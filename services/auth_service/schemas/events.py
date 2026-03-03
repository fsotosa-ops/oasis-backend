from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import List, Optional

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
    background_end_color: Optional[str] = None
    gradient_direction: Optional[str] = "to-b"
    background_image_url: Optional[str] = None
    text_color: Optional[str] = "#FFFFFF"
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
    journey_ids: List[UUID4] = []
    landing_config: LandingConfig = Field(default_factory=LandingConfig)
    notes: Optional[str] = None
    expected_participants: Optional[int] = None


class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[EventStatus] = None
    journey_ids: Optional[List[UUID4]] = None
    landing_config: Optional[LandingConfig] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    expected_participants: Optional[int] = None


class EventResponse(BaseModel):
    id: str
    organization_id: str
    journey_ids: List[str] = []
    name: str
    slug: str
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus
    landing_config: LandingConfig
    is_active: bool
    notes: Optional[str] = None
    expected_participants: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class JourneySummary(BaseModel):
    id: str
    title: str


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
    journey_ids: List[str] = []
    journey_summaries: List[JourneySummary] = []
