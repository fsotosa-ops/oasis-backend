from datetime import datetime

from pydantic import UUID4, BaseModel, Field


class GamificationConfigCreate(BaseModel):
    points_enabled: bool = True
    levels_enabled: bool = True
    rewards_enabled: bool = True
    points_multiplier: float = Field(default=1.00, ge=0.01, le=99.99)
    default_step_points: int = Field(default=10, ge=0)
    profile_completion_points: int = Field(default=0, ge=0)


class GamificationConfigUpdate(BaseModel):
    points_enabled: bool | None = None
    levels_enabled: bool | None = None
    rewards_enabled: bool | None = None
    points_multiplier: float | None = Field(default=None, ge=0.01, le=99.99)
    default_step_points: int | None = Field(default=None, ge=0)
    profile_completion_points: int | None = Field(default=None, ge=0)


class GamificationConfigRead(BaseModel):
    id: UUID4
    organization_id: UUID4
    points_enabled: bool = True
    levels_enabled: bool = True
    rewards_enabled: bool = True
    points_multiplier: float = 1.00
    default_step_points: int = 10
    profile_completion_points: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
