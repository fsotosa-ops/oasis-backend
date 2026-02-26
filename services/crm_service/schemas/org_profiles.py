from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OrgProfileUpdate(BaseModel):
    website: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    address: Optional[str] = None


class OrgProfileResponse(BaseModel):
    org_id: UUID
    website: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    address: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
