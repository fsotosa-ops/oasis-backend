from uuid import UUID

from supabase import AsyncClient


async def get_user_total_points(db: AsyncClient, user_id: UUID) -> int:
    response = (
        await db.schema("journeys").table("points_ledger")
        .select("amount")
        .eq("user_id", str(user_id))
        .execute()
    )
    entries = response.data or []
    return sum(e["amount"] for e in entries)


async def get_user_activities(
    db: AsyncClient, user_id: UUID, limit: int = 20
) -> list[dict]:
    response = (
        await db.schema("journeys").table("user_activities")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []


async def get_user_points_ledger(
    db: AsyncClient, user_id: UUID, limit: int = 50
) -> list[dict]:
    response = (
        await db.schema("journeys").table("points_ledger")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []
