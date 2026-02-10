from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class NoteCreate(BaseModel):
    content: str
    tags: Optional[List[str]] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class NoteResponse(BaseModel):
    id: UUID
    contact_user_id: UUID
    organization_id: UUID
    author_id: Optional[UUID] = None
    content: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
