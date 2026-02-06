from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enums (espejan los DB enums)
# ---------------------------------------------------------------------------
class AccountStatus(StrEnum):
    active = "active"
    suspended = "suspended"
    pending_verification = "pending_verification"
    deleted = "deleted"


class OrgType(StrEnum):
    community = "community"
    provider = "provider"
    sponsor = "sponsor"
    enterprise = "enterprise"


class MemberRole(StrEnum):
    owner = "owner"
    admin = "admin"
    facilitador = "facilitador"
    participante = "participante"


class MembershipStatus(StrEnum):
    active = "active"
    invited = "invited"
    suspended = "suspended"
    inactive = "inactive"


# ---------------------------------------------------------------------------
# Auth request schemas
# ---------------------------------------------------------------------------
class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordUpdate(BaseModel):
    new_password: str = Field(..., min_length=8)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Auth response schemas
# ---------------------------------------------------------------------------
class OrgMembership(BaseModel):
    id: str
    organization_id: str
    role: MemberRole
    status: MembershipStatus
    joined_at: Optional[datetime] = None
    organization_name: Optional[str] = None
    organization_slug: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_platform_admin: bool = False
    status: AccountStatus = AccountStatus.active
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    organizations: list[OrgMembership] = []


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class OAuthUrlResponse(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Organization schemas
# ---------------------------------------------------------------------------
class AdminUserUpdate(BaseModel):
    is_platform_admin: bool


class PaginatedUsersResponse(BaseModel):
    users: list[UserResponse]
    count: int


# ---------------------------------------------------------------------------
# Organization schemas
# ---------------------------------------------------------------------------
class OrgCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: Optional[str] = None
    logo_url: Optional[str] = None
    type: OrgType = OrgType.provider
    settings: Optional[dict] = None
    owner_user_id: Optional[str] = Field(None, description="UUID del usuario que sera owner. Si no se envia, el admin creador queda como owner.")


class OrgUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    settings: Optional[dict] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    type: OrgType
    settings: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Member schemas
# ---------------------------------------------------------------------------
class MemberInvite(BaseModel):
    user_id: str
    role: MemberRole = MemberRole.participante


class MemberUpdate(BaseModel):
    role: Optional[MemberRole] = None
    status: Optional[MembershipStatus] = None


class MemberUserProfile(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    is_platform_admin: bool = False


class MemberResponse(BaseModel):
    id: str
    organization_id: str
    user_id: str
    role: MemberRole
    status: MembershipStatus
    invited_by: Optional[str] = None
    invited_at: Optional[datetime] = None
    joined_at: Optional[datetime] = None
    user: Optional[MemberUserProfile] = None
