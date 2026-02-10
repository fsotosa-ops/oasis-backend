from uuid import UUID

from supabase import AsyncClient


async def evaluate_unlock(
    db: AsyncClient,
    resource: dict,
    user_id: UUID,
) -> tuple[bool, list[str]]:
    """
    Evaluate whether a user has met the unlock conditions for a resource.
    Returns (is_unlocked, lock_reasons).
    """
    conditions = await _get_conditions(db, resource["id"])

    if not conditions:
        return True, []

    # Batch-fetch user data
    user_data = await _fetch_user_data(db, user_id)

    results = []
    lock_reasons = []

    for cond in conditions:
        met, reason = await _evaluate_condition(db, cond, user_data)
        results.append(met)
        if not met and reason:
            lock_reasons.append(reason)

    unlock_logic = resource.get("unlock_logic", "AND")

    if unlock_logic == "AND":
        is_unlocked = all(results)
    else:  # OR
        is_unlocked = any(results)

    if is_unlocked:
        lock_reasons = []

    return is_unlocked, lock_reasons


async def _get_conditions(db: AsyncClient, resource_id: str) -> list[dict]:
    response = (
        await db.schema("resources").table("resource_unlock_conditions")
        .select("*")
        .eq("resource_id", resource_id)
        .execute()
    )
    return response.data or []


async def _fetch_user_data(db: AsyncClient, user_id: UUID) -> dict:
    user_id_str = str(user_id)

    # Total points
    pts_resp = (
        await db.schema("journeys").table("points_ledger")
        .select("amount")
        .eq("user_id", user_id_str)
        .execute()
    )
    total_points = sum(e["amount"] for e in (pts_resp.data or []))

    # User rewards
    rewards_resp = (
        await db.schema("journeys").table("user_rewards")
        .select("reward_id")
        .eq("user_id", user_id_str)
        .execute()
    )
    earned_reward_ids = {r["reward_id"] for r in (rewards_resp.data or [])}

    # Completed enrollments
    enroll_resp = (
        await db.schema("journeys").table("enrollments")
        .select("journey_id")
        .eq("user_id", user_id_str)
        .eq("status", "completed")
        .execute()
    )
    completed_journey_ids = {e["journey_id"] for e in (enroll_resp.data or [])}

    # Current level (user's highest level based on points)
    levels_resp = (
        await db.schema("journeys").table("levels")
        .select("id, name, min_points")
        .order("min_points", desc=True)
        .execute()
    )
    current_level_id = None
    for lvl in (levels_resp.data or []):
        if total_points >= lvl["min_points"]:
            current_level_id = lvl["id"]
            break

    # Build levels lookup
    levels_map = {lvl["id"]: lvl for lvl in (levels_resp.data or [])}

    return {
        "total_points": total_points,
        "earned_reward_ids": earned_reward_ids,
        "completed_journey_ids": completed_journey_ids,
        "current_level_id": current_level_id,
        "levels_map": levels_map,
    }


async def _evaluate_condition(
    db: AsyncClient,
    condition: dict,
    user_data: dict,
) -> tuple[bool, str | None]:
    ctype = condition["condition_type"]

    if ctype == "points_threshold":
        required = condition.get("reference_value", 0) or 0
        current = user_data["total_points"]
        if current >= required:
            return True, None
        diff = required - current
        return False, f"Te faltan {diff} puntos para desbloquear"

    elif ctype == "level_required":
        ref_id = condition.get("reference_id")
        if not ref_id:
            return True, None

        required_level = user_data["levels_map"].get(ref_id)
        if not required_level:
            return True, None

        required_min = required_level["min_points"]
        if user_data["total_points"] >= required_min:
            return True, None

        return False, f"Necesitas alcanzar el nivel {required_level['name']}"

    elif ctype == "reward_required":
        ref_id = condition.get("reference_id")
        if not ref_id:
            return True, None

        if ref_id in user_data["earned_reward_ids"]:
            return True, None

        # Get reward name for message
        reward_resp = (
            await db.schema("journeys").table("rewards_catalog")
            .select("name")
            .eq("id", ref_id)
            .execute()
        )
        reward_name = (reward_resp.data[0]["name"] if reward_resp.data else "desconocido")
        return False, f"Necesitas obtener el badge {reward_name}"

    elif ctype == "journey_completed":
        ref_id = condition.get("reference_id")
        if not ref_id:
            return True, None

        if ref_id in user_data["completed_journey_ids"]:
            return True, None

        # Get journey title for message
        journey_resp = (
            await db.schema("journeys").table("journeys")
            .select("title")
            .eq("id", ref_id)
            .execute()
        )
        journey_title = (journey_resp.data[0]["title"] if journey_resp.data else "desconocido")
        return False, f"Completa el Journey {journey_title} para desbloquear"

    return True, None
