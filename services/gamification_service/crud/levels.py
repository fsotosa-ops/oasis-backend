from uuid import UUID

from supabase import AsyncClient

from services.gamification_service.schemas.levels import LevelCreate, LevelUpdate


async def list_levels(db: AsyncClient, org_id: UUID) -> list[dict]:
    response = (
        await db.schema("journeys").table("levels")
        .select("*")
        .or_(f"organization_id.eq.{org_id},organization_id.is.null")
        .order("min_points")
        .execute()
    )
    return response.data or []


async def get_level(db: AsyncClient, level_id: UUID) -> dict | None:
    response = (
        await db.schema("journeys").table("levels")
        .select("*")
        .eq("id", str(level_id))
        .single()
        .execute()
    )
    return response.data


async def create_level(db: AsyncClient, org_id: UUID, level: LevelCreate) -> dict:
    payload = {
        "organization_id": str(org_id),
        "name": level.name,
        "min_points": level.min_points,
        "icon_url": level.icon_url,
        "benefits": level.benefits,
    }
    response = await db.schema("journeys").table("levels").insert(payload).execute()
    return response.data[0] if response.data else {}


async def update_level(db: AsyncClient, level_id: UUID, level: LevelUpdate) -> dict:
    payload = {}
    if level.name is not None:
        payload["name"] = level.name
    if level.min_points is not None:
        payload["min_points"] = level.min_points
    if level.icon_url is not None:
        payload["icon_url"] = level.icon_url
    if level.benefits is not None:
        payload["benefits"] = level.benefits

    if not payload:
        return await get_level(db, level_id) or {}

    response = (
        await db.schema("journeys").table("levels")
        .update(payload)
        .eq("id", str(level_id))
        .execute()
    )
    return response.data[0] if response.data else {}


async def delete_level(db: AsyncClient, level_id: UUID) -> bool:
    response = (
        await db.schema("journeys").table("levels")
        .delete()
        .eq("id", str(level_id))
        .execute()
    )
    return len(response.data) > 0 if response.data else False
