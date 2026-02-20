from datetime import datetime

from pydantic import UUID4, BaseModel, Field


class UnlockCondition(BaseModel):
    """Condición de desbloqueo de una recompensa.

    Estructura multi-condición:
        {
          "operator": "AND" | "OR",
          "conditions": [
            {"type": "profile_completion"},
            {"type": "min_points", "value": 100},
            {"type": "journey_completed", "journey_id": "<uuid>"}
          ]
        }

    Tipos de condición soportados:
    - "profile_completion" : el usuario completa su perfil CRM.
    - "min_points"         : el usuario acumula al menos `value` puntos.
    - "journey_completed"  : el usuario completa el journey con id `journey_id`.
    """
    operator: str = Field(default="AND", pattern="^(AND|OR)$")
    conditions: list[dict] = Field(default_factory=list)


class RewardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    type: str = Field(..., min_length=1, max_length=50)
    icon_url: str | None = None
    points: int = Field(default=0, ge=0, description="Puntos otorgados al ganar esta recompensa")
    unlock_condition: UnlockCondition = Field(default_factory=UnlockCondition)


class RewardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    type: str | None = Field(None, min_length=1, max_length=50)
    icon_url: str | None = None
    points: int | None = Field(None, ge=0)
    unlock_condition: UnlockCondition | None = None


class RewardRead(BaseModel):
    id: UUID4
    organization_id: UUID4 | None = None
    name: str
    description: str | None = None
    type: str
    icon_url: str | None = None
    points: int = 0
    unlock_condition: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class UserRewardRead(BaseModel):
    id: UUID4
    user_id: UUID4
    reward_id: UUID4
    earned_at: datetime
    journey_id: UUID4 | None = None
    metadata: dict = Field(default_factory=dict)
    reward: RewardRead | None = None

    class Config:
        from_attributes = True


class UserRewardGrant(BaseModel):
    user_id: UUID4
    reward_id: UUID4
    journey_id: UUID4 | None = None
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reward-Organization assignment
# ---------------------------------------------------------------------------

class RewardOrganizationRead(BaseModel):
    id: UUID4
    reward_id: UUID4
    organization_id: UUID4
    assigned_at: datetime
    org_name: str | None = None
    org_slug: str | None = None

    class Config:
        from_attributes = True


class RewardOrganizationsResponse(BaseModel):
    reward_id: UUID4
    organizations: list[RewardOrganizationRead]
    total: int


class RewardOrganizationAssign(BaseModel):
    organization_ids: list[UUID4]


class RewardOrganizationUnassign(BaseModel):
    organization_ids: list[UUID4]
