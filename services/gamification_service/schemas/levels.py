from datetime import datetime

from pydantic import UUID4, BaseModel, Field


class LevelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    min_points: int = Field(..., ge=0)
    icon_url: str | None = None
    benefits: dict = Field(default_factory=dict)


class LevelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    min_points: int | None = Field(None, ge=0)
    icon_url: str | None = None
    benefits: dict | None = None


class LevelRead(BaseModel):
    id: UUID4
    organization_id: UUID4 | None = None
    name: str
    min_points: int
    icon_url: str | None = None
    benefits: dict = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True
