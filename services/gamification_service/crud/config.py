from uuid import UUID

from supabase import AsyncClient

from services.gamification_service.schemas.config import (
    GamificationConfigCreate,
    GamificationConfigUpdate,
)


async def get_config(db: AsyncClient, org_id: UUID) -> dict | None:
    response = (
        await db.schema("journeys").table("gamification_config")
        .select("*")
        .eq("organization_id", str(org_id))
        .maybe_single()
        .execute()
    )
    return response.data


async def upsert_config(
    db: AsyncClient, org_id: UUID, payload: GamificationConfigCreate
) -> dict:
    data = {
        "organization_id": str(org_id),
        **payload.model_dump(mode="json"),
    }
    response = (
        await db.schema("journeys").table("gamification_config")
        .upsert(data, on_conflict="organization_id")
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else {}


async def update_config(
    db: AsyncClient, org_id: UUID, payload: GamificationConfigUpdate
) -> dict | None:
    updates = payload.model_dump(exclude_none=True, mode="json")
    if not updates:
        return await get_config(db, org_id)

    # Use upsert so PATCH works even when no config row exists yet for this org
    existing = await get_config(db, org_id) or {}
    org_id_str = str(org_id)
    merged: dict = {**existing, **updates, "organization_id": org_id_str}
    for key in ("id", "created_at", "updated_at"):
        merged.pop(key, None)

    response = (
        await db.schema("journeys").table("gamification_config")
        .upsert(merged, on_conflict="organization_id")
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None
