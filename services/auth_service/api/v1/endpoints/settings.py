from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from common.auth.security import AdminUser, CurrentUser, get_current_token
from common.database.client import get_admin_client, get_scoped_client
from common.exceptions import NotFoundError

router = APIRouter()


# ---------------------------------------------------------------------------
# Settings shape — extend here as new platform config is needed
# ---------------------------------------------------------------------------

class EventFormsSettings(BaseModel):
    diagnosis_form_url: Optional[str] = None
    closure_form_url: Optional[str] = None


class PlatformSettingsData(BaseModel):
    event_forms: EventFormsSettings = EventFormsSettings()


class PlatformSettingsResponse(BaseModel):
    settings: PlatformSettingsData
    updated_at: datetime
    updated_by: Optional[str] = None


class PlatformSettingsUpdate(BaseModel):
    """Partial update — only supplied keys are merged into the existing settings."""
    event_forms: Optional[EventFormsSettings] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
    row = response.data
    return {
        "settings": PlatformSettingsData(**row.get("settings", {})),
        "updated_at": row["updated_at"],
        "updated_by": row.get("updated_by"),
    }


@router.patch("", response_model=PlatformSettingsResponse)
async def update_platform_settings(
    data: PlatformSettingsUpdate,
    admin: AdminUser,
):
    """
    Merges the supplied keys into the existing settings JSONB.
    Only platform admins can call this endpoint.
    """
    admin_client = await get_admin_client()

    # Fetch current settings to merge
    current_resp = (
        await admin_client.table("platform_settings")
        .select("settings")
        .eq("lock", True)
        .maybe_single()
        .execute()
    )
    if not current_resp.data:
        raise NotFoundError("Platform settings not found")

    current = PlatformSettingsData(**current_resp.data.get("settings", {}))

    # Merge only the supplied sections
    update_data = data.model_dump(exclude_unset=True)
    merged = current.model_dump()
    for section, values in update_data.items():
        if values is not None:
            merged[section] = {**merged.get(section, {}), **values}

    response = (
        await admin_client.table("platform_settings")
        .update({"settings": merged, "updated_by": str(admin.id)})
        .eq("lock", True)
        .execute()
    )
    if not response.data:
        raise NotFoundError("Platform settings not found")

    row = response.data[0]
    return {
        "settings": PlatformSettingsData(**row["settings"]),
        "updated_at": row["updated_at"],
        "updated_by": row.get("updated_by"),
    }
