from datetime import datetime

from pydantic import UUID4, BaseModel, Field

from services.gamification_service.schemas.levels import LevelRead
from services.gamification_service.schemas.rewards import RewardRead, UserRewardRead


class ActivityRead(BaseModel):
    id: UUID4
    user_id: UUID4
    type: str
    points_awarded: int = 0
    organization_id: UUID4 | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class PointsLedgerRead(BaseModel):
    id: UUID4
    user_id: UUID4
    amount: int
    reason: str
    reference_id: UUID4 | None = None
    organization_id: UUID4 | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserPointsSummary(BaseModel):
    total_points: int = 0
    current_level: LevelRead | None = None
    next_level: LevelRead | None = None
    points_to_next_level: int | None = None
    rewards: list[UserRewardRead] = Field(default_factory=list)
    recent_activities: list[ActivityRead] = Field(default_factory=list)
