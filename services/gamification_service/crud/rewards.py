from uuid import UUID

from supabase import AsyncClient

from services.gamification_service.schemas.rewards import RewardCreate, RewardUpdate


async def list_rewards(db: AsyncClient, org_id: UUID) -> list[dict]:
    """Lista recompensas accesibles para una org:
    - De su propiedad (organization_id = org_id)
    - Globales (organization_id IS NULL)
    - Asignadas vía tabla pivot reward_organizations
    """
    # Propias + globales
    owned_resp = (
        await db.schema("journeys").table("rewards_catalog")
        .select("*")
        .or_(f"organization_id.eq.{org_id},organization_id.is.null")
        .execute()
    )
    owned = owned_resp.data or []
    owned_ids = {r["id"] for r in owned}

    # Asignadas vía pivot (no duplicar las ya incluidas)
    pivot_resp = (
        await db.schema("journeys").table("reward_organizations")
        .select("reward_id")
        .eq("organization_id", str(org_id))
        .execute()
    )
    extra_ids = [
        r["reward_id"] for r in (pivot_resp.data or [])
        if r["reward_id"] not in owned_ids
    ]
    if extra_ids:
        extra_resp = (
            await db.schema("journeys").table("rewards_catalog")
            .select("*")
            .in_("id", extra_ids)
            .execute()
        )
        owned.extend(extra_resp.data or [])

    return owned


async def get_reward(db: AsyncClient, reward_id: UUID) -> dict | None:
    response = (
        await db.schema("journeys").table("rewards_catalog")
        .select("*")
        .eq("id", str(reward_id))
        .single()
        .execute()
    )
    return response.data


async def create_reward(db: AsyncClient, org_id: UUID, reward: RewardCreate) -> dict:
    payload = {
        "organization_id": str(org_id),
        "name": reward.name,
        "description": reward.description,
        "type": reward.type,
        "icon_url": reward.icon_url,
        "points": reward.points,
        "unlock_condition": reward.unlock_condition.model_dump(),
    }
    response = await db.schema("journeys").table("rewards_catalog").insert(payload).execute()
    return response.data[0] if response.data else {}


async def update_reward(db: AsyncClient, reward_id: UUID, reward: RewardUpdate) -> dict:
    payload = {}
    if reward.name is not None:
        payload["name"] = reward.name
    if reward.description is not None:
        payload["description"] = reward.description
    if reward.type is not None:
        payload["type"] = reward.type
    if reward.icon_url is not None:
        payload["icon_url"] = reward.icon_url
    if reward.points is not None:
        payload["points"] = reward.points
    if reward.unlock_condition is not None:
        payload["unlock_condition"] = reward.unlock_condition.model_dump()

    if not payload:
        return await get_reward(db, reward_id) or {}

    response = (
        await db.schema("journeys").table("rewards_catalog")
        .update(payload)
        .eq("id", str(reward_id))
        .execute()
    )
    return response.data[0] if response.data else {}


async def delete_reward(db: AsyncClient, reward_id: UUID) -> bool:
    response = (
        await db.schema("journeys").table("rewards_catalog")
        .delete()
        .eq("id", str(reward_id))
        .execute()
    )
    return len(response.data) > 0 if response.data else False
