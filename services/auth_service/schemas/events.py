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


class AttendanceModality(StrEnum):
    presencial = "presencial"
    online = "online"
    hibrido = "hibrido"


class AttendanceStatus(StrEnum):
    registered = "registered"
    attended = "attended"
    no_show = "no_show"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Event JSONB sub-models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------

class EventCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus = EventStatus.upcoming
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
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    expected_participants: Optional[int] = None
    counterpart_details: Optional[EventCounterpartDetails] = None
    venue_details: Optional[EventVenueDetails] = None
    diagnosis: Optional[EventDiagnosis] = None


class EventResponse(BaseModel):
    id: str
    organization_id: str
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
    # Computed via join — populated by EventManager
    journey_ids: List[str] = []
    attendance_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Event ↔ Journey assignment
# ---------------------------------------------------------------------------

class EventJourneyAdd(BaseModel):
    journey_id: UUID4


class EventJourneyResponse(BaseModel):
    id: str
    event_id: str
    journey_id: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class JoinEventResponse(BaseModel):
    event_id: str
    org_joined: bool
    attendance_registered: bool
    journey_enrolled: str | None = None


class AttendanceCreate(BaseModel):
    user_id: UUID4
    modality: AttendanceModality = AttendanceModality.presencial
    notes: Optional[str] = None


class AttendanceUpdate(BaseModel):
    status: Optional[AttendanceStatus] = None
    modality: Optional[AttendanceModality] = None
    notes: Optional[str] = None


class AttendanceResponse(BaseModel):
    id: str
    event_id: str
    user_id: str
    modality: AttendanceModality
    status: AttendanceStatus
    registered_at: datetime
    checked_in_at: Optional[datetime] = None
    notes: Optional[str] = None
    # Populated via join with profiles
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
