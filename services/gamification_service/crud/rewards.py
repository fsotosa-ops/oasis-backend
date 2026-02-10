from uuid import UUID

from supabase import AsyncClient

from services.gamification_service.schemas.rewards import RewardCreate, RewardUpdate


async def list_rewards(db: AsyncClient, org_id: UUID) -> list[dict]:
    response = (
        await db.schema("journeys").table("rewards_catalog")
        .select("*")
        .or_(f"organization_id.eq.{org_id},organization_id.is.null")
        .execute()
    )
    return response.data or []


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
        "unlock_condition": reward.unlock_condition,
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
    if reward.unlock_condition is not None:
        payload["unlock_condition"] = reward.unlock_condition

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
