from datetime import datetime
from typing import Any, Literal

from pydantic import UUID4, BaseModel, Field

StepType = Literal[
    "survey",
    "event_attendance",
    "content_view",
    "milestone",
    "social_interaction",
    "resource_consumption",
]


class GamificationRules(BaseModel):
    base_points: int = 0
    bonus_rules: dict[str, Any] | None = Field(
        default=None, description="Reglas extra ej: {'min_duration': 60, 'bonus': 5}"
    )


# ---------------------------------------------------------------------------
# Step schemas
# ---------------------------------------------------------------------------
class StepBase(BaseModel):
    title: str
    type: StepType
    gamification_rules: GamificationRules = Field(default_factory=GamificationRules)
    config: dict[str, Any] = Field(default_factory=dict)


class StepRead(StepBase):
    id: UUID4
    journey_id: UUID4
    order_index: int = 0

    class Config:
        from_attributes = True


class StepCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    type: StepType
    order_index: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    gamification_rules: GamificationRules = Field(default_factory=GamificationRules)


class StepUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    type: StepType | None = None
    config: dict[str, Any] | None = None
    gamification_rules: GamificationRules | None = None


class StepAdminRead(BaseModel):
    id: UUID4
    journey_id: UUID4
    title: str
    type: StepType
    order_index: int
    config: dict = Field(default_factory=dict)
    gamification_rules: GamificationRules = Field(default_factory=GamificationRules)
    created_at: datetime
    updated_at: datetime
    total_completions: int = 0
    average_points: float = 0.0

    class Config:
        from_attributes = True


class StepReorderItem(BaseModel):
    step_id: UUID4
    new_index: int = Field(..., ge=0)


class StepReorderRequest(BaseModel):
    steps: list[StepReorderItem] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Journey schemas
# ---------------------------------------------------------------------------
class JourneyBase(BaseModel):
    title: str
    slug: str
    description: str | None = None
    is_active: bool = True
    metadata: dict = Field(default_factory=dict)


class JourneyRead(JourneyBase):
    id: UUID4
    organization_id: UUID4
    created_at: datetime
    steps: list[StepRead] = []

    class Config:
        from_attributes = True


class JourneyCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    thumbnail_url: str | None = None
    is_active: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class JourneyUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    slug: str | None = Field(
        None, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$"
    )
    description: str | None = None
    thumbnail_url: str | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class JourneyAdminRead(BaseModel):
    id: UUID4
    organization_id: UUID4
    title: str
    slug: str
    description: str | None = None
    thumbnail_url: str | None = None
    is_active: bool
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    total_steps: int = 0
    total_enrollments: int = 0
    active_enrollments: int = 0
    completed_enrollments: int = 0
    completion_rate: float = 0.0

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Journey Organization (multi-org assignment) schemas
# ---------------------------------------------------------------------------
class JourneyOrganizationAssign(BaseModel):
    organization_ids: list[UUID4] = Field(..., min_length=1)


class JourneyOrganizationUnassign(BaseModel):
    organization_ids: list[UUID4] = Field(..., min_length=1)


class JourneyOrganizationRead(BaseModel):
    id: UUID4
    journey_id: UUID4
    organization_id: UUID4
    assigned_at: datetime
    assigned_by: UUID4 | None = None

    class Config:
        from_attributes = True


class JourneyOrganizationsResponse(BaseModel):
    journey_id: UUID4
    organizations: list[JourneyOrganizationRead] = []
    total: int = 0
