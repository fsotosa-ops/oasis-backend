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


class EventCounterpartDetails(BaseModel):
    address: Optional[str] = None
    full_entity_name: Optional[str] = None
    entity_logo_url: Optional[str] = None
    counterpart_details: Optional[str] = None
    activity_schedule: Optional[str] = None
    expected_ages: Optional[List[str]] = None
    expected_roles: Optional[List[str]] = None
    activity_modality: Optional[str] = None
    specific_activity: Optional[str] = None


class EventVenueDetails(BaseModel):
    has_internet: bool = False
    has_ac: bool = False
    has_lighting: bool = False
    has_technical_rider: bool = False
    notes: Optional[str] = None


class EventDiagnosis(BaseModel):
    objective: Optional[str] = None
    expectations: Optional[str] = None
    historical_activities: Optional[str] = None
    historical_incidents: Optional[str] = None
    myths_stigmas: Optional[str] = None
    community_leaders: Optional[str] = None
    main_obstacles: Optional[str] = None


class EventCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus = EventStatus.upcoming
    journey_ids: List[UUID4] = []
    notes: Optional[str] = None
    expected_participants: Optional[int] = None
    counterpart_details: EventCounterpartDetails = Field(default_factory=EventCounterpartDetails)
    venue_details: EventVenueDetails = Field(default_factory=EventVenueDetails)
    diagnosis: EventDiagnosis = Field(default_factory=EventDiagnosis)


class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[EventStatus] = None
    journey_ids: Optional[List[UUID4]] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    expected_participants: Optional[int] = None
    counterpart_details: Optional[EventCounterpartDetails] = None
    venue_details: Optional[EventVenueDetails] = None
    diagnosis: Optional[EventDiagnosis] = None


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
    is_active: bool
    notes: Optional[str] = None
    expected_participants: Optional[int] = None
    counterpart_details: EventCounterpartDetails = Field(default_factory=EventCounterpartDetails)
    venue_details: EventVenueDetails = Field(default_factory=EventVenueDetails)
    diagnosis: EventDiagnosis = Field(default_factory=EventDiagnosis)
    created_at: datetime
    updated_at: datetime
