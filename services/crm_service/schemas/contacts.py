from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID


class ContactBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    # Location (hierarchical)
    country: Optional[str] = None   # ISO country code, e.g. "CL"
    state: Optional[str] = None     # region / department / province
    city: Optional[str] = None
    # Demographics
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    education_level: Optional[str] = None
    occupation: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = "active"


class ContactUpdate(ContactBase):
    pass


class ContactResponse(ContactBase):
    user_id: UUID
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    oasis_score: Optional[int] = 0

    class Config:
        from_attributes = True


class PaginatedContactsResponse(BaseModel):
    contacts: List[ContactResponse]
    count: int


class ContactEventParticipation(BaseModel):
    # Primary: attendance record (always present)
    attendance_id: str
    attendance_status: str
    modality: Optional[str] = None
    registered_at: Optional[datetime] = None
    checked_in_at: Optional[datetime] = None
    # Event
    event_id: str
    event_name: str
    event_slug: str
    event_status: str
    event_start_date: Optional[datetime] = None
    event_location: Optional[str] = None
    # Org
    org_id: str
    org_name: str
    org_slug: str
    # Optional: enrollment traceability (only if a journey was assigned)
    enrollment_id: Optional[str] = None
    enrollment_status: Optional[str] = None
    journey_id: Optional[str] = None
    enrolled_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Event assignment (admin-side)
# ---------------------------------------------------------------------------

class AssignEventRequest(BaseModel):
    event_id: str
    modality: str = "presencial"


class AssignEventResponse(BaseModel):
    event_id: str
    organization_id: str
    org_joined: bool
    attendance_registered: bool
    journeys_enrolled: list[str]


# ---------------------------------------------------------------------------
# Field Options (configurable select options for gender, education, occupation)
# ---------------------------------------------------------------------------

class FieldOptionBase(BaseModel):
    field_name: str
    value: str
    label: str
    sort_order: int = 0
    is_active: bool = True


class FieldOptionCreate(FieldOptionBase):
    pass


class FieldOptionUpdate(BaseModel):
    label: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class FieldOptionResponse(FieldOptionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True