from datetime import datetime
from typing import Literal

from pydantic import UUID4, BaseModel, Field


class RewardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    type: Literal["badge", "points"]
    icon_url: str | None = None
    unlock_condition: dict = Field(default_factory=dict)


class RewardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    type: Literal["badge", "points"] | None = None
    icon_url: str | None = None
    unlock_condition: dict | None = None


class RewardRead(BaseModel):
    id: UUID4
    organization_id: UUID4 | None = None
    name: str
    description: str | None = None
    type: str
    icon_url: str | None = None
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
