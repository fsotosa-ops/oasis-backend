from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ContactBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = "active"

class ContactUpdate(ContactBase):
    pass

class ContactResponse(ContactBase):
    user_id: UUID
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    
    # Optional fields populated via joins or aggregation
    oasis_score: Optional[int] = 0
    
    class Config:
        from_attributes = True