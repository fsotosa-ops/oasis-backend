from uuid import UUID

from supabase import AsyncClient

from services.gamification_service.schemas.rewards import UserRewardGrant


async def get_user_rewards(db: AsyncClient, user_id: UUID) -> list[dict]:
    response = (
        await db.schema("journeys").table("user_rewards")
        .select("*, rewards_catalog(*)")
        .eq("user_id", str(user_id))
        .order("earned_at", desc=True)
        .execute()
    )
    rewards = response.data or []

    # Flatten the joined reward data
    for r in rewards:
        catalog = r.pop("rewards_catalog", None)
        r["reward"] = catalog

    # Deduplicate by reward_id: keep only the most recent grant per reward
    # (rows are already ordered by earned_at DESC so first occurrence = most recent).
    seen_reward_ids: set[str] = set()
    unique_rewards = []
    for r in rewards:
        rid = str(r.get("reward_id", ""))
        if rid and rid in seen_reward_ids:
            continue
        seen_reward_ids.add(rid)
        unique_rewards.append(r)

    return unique_rewards


async def get_user_rewards_for_admin(db: AsyncClient, user_id: UUID) -> list[dict]:
    return await get_user_rewards(db, user_id)


async def grant_reward(db: AsyncClient, grant: UserRewardGrant) -> dict:
    payload = {
        "user_id": str(grant.user_id),
        "reward_id": str(grant.reward_id),
        "metadata": grant.metadata,
    }
    if grant.journey_id:
        payload["journey_id"] = str(grant.journey_id)

    response = (
        await db.schema("journeys").table("user_rewards")
        .insert(payload)
        .execute()
    )
    return response.data[0] if response.data else {}


async def revoke_reward(db: AsyncClient, user_reward_id: UUID) -> bool:
    response = (
        await db.schema("journeys").table("user_rewards")
        .delete()
        .eq("id", str(user_reward_id))
        .execute()
    )
    return len(response.data) > 0 if response.data else False
