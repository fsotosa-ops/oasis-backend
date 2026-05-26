from fastapi import APIRouter, Depends

from common.auth.security import AdminUser, CurrentUser, get_current_token
from common.database.client import get_admin_client, get_scoped_client
from common.exceptions import NotFoundError
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime

router = APIRouter()


class PlatformSettingsResponse(BaseModel):
    diagnosis_form_url: Optional[str] = None
    closure_form_url: Optional[str] = None
    updated_at: datetime
    updated_by: Optional[str] = None


class PlatformSettingsUpdate(BaseModel):
    diagnosis_form_url: Optional[str] = None
    closure_form_url: Optional[str] = None


@router.get("", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    user: CurrentUser,
    token: str = Depends(get_current_token),
):
    """Returns platform-wide settings. Readable by any authenticated user."""
    client = await get_scoped_client(token)
    response = await client.table("platform_settings").select("*").maybe_single().execute()
    if not response.data:
        raise NotFoundError("Platform settings not found")
    return response.data


@router.patch("", response_model=PlatformSettingsResponse)
async def update_platform_settings(
    data: PlatformSettingsUpdate,
    admin: AdminUser,
):
    """Updates platform-wide settings. Restricted to platform admins."""
    payload = data.model_dump(exclude_unset=True)
    payload["updated_by"] = str(admin.id)

    client = await get_admin_client()
    response = (
        await client.table("platform_settings")
        .update(payload)
        .eq("lock", True)
        .execute()
    )
    if not response.data:
        raise NotFoundError("Platform settings not found")
    return response.data[0]
