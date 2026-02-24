from uuid import UUID

from supabase import AsyncClient


async def get_user_total_points(
    db: AsyncClient, user_id: UUID, org_id: UUID | None = None
) -> int:
    query = (
        db.schema("journeys").table("points_ledger")
        .select("amount, reference_id")
        .eq("user_id", str(user_id))
    )
    if org_id:
        query = query.eq("organization_id", str(org_id))
    # Order newest first so first occurrence of each reference_id is the most recent
    response = await query.order("created_at", desc=True).execute()
    entries = response.data or []

    # Deduplicate by reference_id: for rewards/events with a reference_id, count
    # only the most recent entry. Entries without reference_id (e.g. manual adjustments)
    # are always counted.
    seen_refs: set[str] = set()
    total = 0
    for e in entries:
        ref = e.get("reference_id")
        if ref is not None:
            if ref in seen_refs:
                continue  # duplicate — skip older entry
            seen_refs.add(ref)
        total += e["amount"]
    return total


async def get_user_activities(
    db: AsyncClient, user_id: UUID, org_id: UUID | None = None, limit: int = 20
) -> list[dict]:
    query = (
        db.schema("journeys").table("user_activities")
        .select("*")
        .eq("user_id", str(user_id))
    )
    if org_id:
        query = query.eq("organization_id", str(org_id))
    # Fetch more rows than needed so we have enough after deduplication
    response = await query.order("created_at", desc=True).limit(limit * 4).execute()
    raw = response.data or []

    # Deduplicate: for activity types that carry a stable reference, keep only the
    # most recent occurrence (rows are already ordered newest-first).
    seen_keys: set[str] = set()
    result = []
    for entry in raw:
        act_type = entry.get("type", "")
        meta = entry.get("metadata") or {}
        ref = None
        if act_type == "profile_completed":
            ref = meta.get("reward_id")
        elif act_type == "step_completed":
            ref = meta.get("step_id")
        elif act_type == "journey_completed":
            ref = meta.get("journey_id")
        if ref is not None:
            key = f"{act_type}:{ref}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
        result.append(entry)
    return result[:limit]


async def get_user_points_ledger(
    db: AsyncClient, user_id: UUID, org_id: UUID | None = None, limit: int = 50
) -> list[dict]:
    query = (
        db.schema("journeys").table("points_ledger")
        .select("*")
        .eq("user_id", str(user_id))
    )
    if org_id:
        query = query.eq("organization_id", str(org_id))
    response = await query.order("created_at", desc=True).limit(limit).execute()
    return response.data or []
