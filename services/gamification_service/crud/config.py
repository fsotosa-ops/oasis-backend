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

    response = (
        await db.schema("journeys").table("gamification_config")
        .update(updates)
        .eq("organization_id", str(org_id))
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None
