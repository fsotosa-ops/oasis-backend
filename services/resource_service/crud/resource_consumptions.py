from uuid import UUID

from supabase import AsyncClient


async def get_user_consumption(
    db: AsyncClient,
    resource_id: UUID,
    user_id: UUID,
) -> dict | None:
    response = (
        await db.schema("resources").table("resource_consumptions")
        .select("*")
        .eq("resource_id", str(resource_id))
        .eq("user_id", str(user_id))
        .execute()
    )
    data = response.data or []
    return data[0] if data else None


async def open_resource(
    db: AsyncClient,
    resource_id: UUID,
    user_id: UUID,
) -> dict:
    existing = await get_user_consumption(db, resource_id, user_id)
    if existing:
        return existing

    response = (
        await db.schema("resources").table("resource_consumptions")
        .insert({
            "resource_id": str(resource_id),
            "user_id": str(user_id),
        })
        .execute()
    )
    return response.data[0] if response.data else {}


async def complete_resource(
    db: AsyncClient,
    resource_id: UUID,
    user_id: UUID,
    points_to_award: int,
    time_on_page_seconds: int = 0,
) -> dict:
    existing = await get_user_consumption(db, resource_id, user_id)

    if existing and existing.get("completed_at"):
        return existing

    if existing:
        response = (
            await db.schema("resources").table("resource_consumptions")
            .update({
                "completed_at": "now()",
                "points_awarded": points_to_award,
                "time_on_page_seconds": time_on_page_seconds,
            })
            .eq("id", existing["id"])
            .execute()
        )
    else:
        response = (
            await db.schema("resources").table("resource_consumptions")
            .insert({
                "resource_id": str(resource_id),
                "user_id": str(user_id),
                "completed_at": "now()",
                "points_awarded": points_to_award,
                "time_on_page_seconds": time_on_page_seconds,
            })
            .execute()
        )

    consumption = response.data[0] if response.data else {}

    # Award points via points_ledger
    if points_to_award > 0:
        await db.schema("journeys").table("points_ledger").insert({
            "user_id": str(user_id),
            "amount": points_to_award,
            "reason": "resource_completion",
            "reference_id": str(resource_id),
        }).execute()

        # Log activity
        await db.schema("journeys").table("user_activities").insert({
            "user_id": str(user_id),
            "type": "resource_completed",
            "points_awarded": points_to_award,
            "metadata": {
                "resource_id": str(resource_id),
            },
        }).execute()

    return consumption


async def get_user_consumptions_batch(
    db: AsyncClient,
    user_id: UUID,
    resource_ids: list[str],
) -> dict[str, dict]:
    if not resource_ids:
        return {}

    response = (
        await db.schema("resources").table("resource_consumptions")
        .select("*")
        .eq("user_id", str(user_id))
        .in_("resource_id", resource_ids)
        .execute()
    )
    consumptions = response.data or []
    return {c["resource_id"]: c for c in consumptions}
