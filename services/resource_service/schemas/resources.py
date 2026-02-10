from datetime import datetime

from pydantic import UUID4, BaseModel, Field


# --- Resource Types ---

class UnlockConditionCreate(BaseModel):
    condition_type: str = Field(..., pattern="^(points_threshold|level_required|reward_required|journey_completed)$")
    reference_id: UUID4 | None = None
    reference_value: int | None = None


class UnlockConditionRead(BaseModel):
    id: UUID4
    resource_id: UUID4
    condition_type: str
    reference_id: UUID4 | None = None
    reference_value: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Resource CRUD ---

class ResourceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None
    type: str = Field(..., pattern="^(video|podcast|pdf|capsula|actividad)$")
    content_url: str | None = None
    thumbnail_url: str | None = None
    points_on_completion: int = Field(default=0, ge=0)
    unlock_logic: str = Field(default="AND", pattern="^(AND|OR)$")
    metadata: dict = Field(default_factory=dict)
    unlock_conditions: list[UnlockConditionCreate] = Field(default_factory=list)


class ResourceUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    type: str | None = Field(None, pattern="^(video|podcast|pdf|capsula|actividad)$")
    content_url: str | None = None
    thumbnail_url: str | None = None
    points_on_completion: int | None = Field(None, ge=0)
    unlock_logic: str | None = Field(None, pattern="^(AND|OR)$")
    metadata: dict | None = None
    unlock_conditions: list[UnlockConditionCreate] | None = None


class ResourceAdminRead(BaseModel):
    id: UUID4
    organization_id: UUID4
    title: str
    description: str | None = None
    type: str
    content_url: str | None = None
    storage_path: str | None = None
    thumbnail_url: str | None = None
    is_published: bool
    points_on_completion: int
    unlock_logic: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    unlock_conditions: list[UnlockConditionRead] = Field(default_factory=list)
    consumption_count: int = 0

    class Config:
        from_attributes = True


# --- Participant View ---

class ResourceParticipantRead(BaseModel):
    id: UUID4
    title: str
    description: str | None = None
    type: str
    content_url: str | None = None
    storage_path: str | None = None
    thumbnail_url: str | None = None
    points_on_completion: int
    is_unlocked: bool = True
    is_consumed: bool = False
    lock_reasons: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


# --- Consumption ---

class ConsumptionCreate(BaseModel):
    time_on_page_seconds: int = Field(default=0, ge=0)


class ConsumptionRead(BaseModel):
    id: UUID4
    resource_id: UUID4
    user_id: UUID4
    opened_at: datetime
    completed_at: datetime | None = None
    time_on_page_seconds: int = 0
    points_awarded: int = 0

    class Config:
        from_attributes = True


# --- Resource Organization ---

class ResourceOrganizationAssign(BaseModel):
    organization_ids: list[UUID4]


class ResourceOrganizationUnassign(BaseModel):
    organization_ids: list[UUID4]


class ResourceOrganizationRead(BaseModel):
    id: UUID4
    resource_id: UUID4
    organization_id: UUID4
    assigned_at: datetime
    assigned_by: UUID4 | None = None

    class Config:
        from_attributes = True


class ResourceOrganizationsResponse(BaseModel):
    resource_id: UUID4
    organizations: list[ResourceOrganizationRead]
    total: int
