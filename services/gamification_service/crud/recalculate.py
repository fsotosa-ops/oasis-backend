from uuid import UUID

from supabase import AsyncClient


async def recalculate_points(
    db: AsyncClient,
    org_id: UUID,
    journey_id: UUID | None = None,
) -> int:
    """Recalculate points for existing step_completions using current base_points.

    For each step_completion in the org (optionally filtered by journey):
      1. Read the step's current gamification_rules.base_points
      2. Apply the org's points_multiplier
      3. Update step_completions.points_earned
      4. Update the corresponding points_ledger entry

    Returns the number of step_completions updated.
    """
    org_str = str(org_id)

    # 1. Load org multiplier
    config_resp = (
        await db.schema("journeys")
        .table("gamification_config")
        .select("points_multiplier, default_step_points")
        .eq("organization_id", org_str)
        .maybe_single()
        .execute()
    )
    multiplier = 1.0
    default_points = 10
    if config_resp.data:
        multiplier = float(config_resp.data.get("points_multiplier", 1.0))
        default_points = int(config_resp.data.get("default_step_points", 10))

    # 2. Load all steps for the org (or specific journey)
    journeys_query = (
        db.schema("journeys")
        .table("journeys")
        .select("id")
        .eq("organization_id", org_str)
    )
    if journey_id:
        journeys_query = journeys_query.eq("id", str(journey_id))
    journeys_resp = await journeys_query.execute()
    journey_ids = [j["id"] for j in (journeys_resp.data or [])]

    if not journey_ids:
        return 0

    # 3. Load steps with their current base_points
    steps_resp = (
        await db.schema("journeys")
        .table("steps")
        .select("id, gamification_rules")
        .in_("journey_id", journey_ids)
        .execute()
    )
    steps = steps_resp.data or []

    # Build step_id → new_points map
    step_points: dict[str, int] = {}
    for step in steps:
        rules = step.get("gamification_rules") or {}
        base = rules.get("base_points")
        if base is not None:
            step_points[step["id"]] = round(int(base) * multiplier)
        else:
            step_points[step["id"]] = round(default_points * multiplier)

    # 4. Load all step_completions for these steps
    step_ids = list(step_points.keys())
    if not step_ids:
        return 0

    completions_resp = (
        await db.schema("journeys")
        .table("step_completions")
        .select("id, step_id, points_earned")
        .in_("step_id", step_ids)
        .execute()
    )
    completions = completions_resp.data or []

    # 5. Update each completion where points differ
    updated = 0
    for comp in completions:
        new_points = step_points.get(comp["step_id"], 0)
        if comp["points_earned"] == new_points:
            continue

        # Update step_completions.points_earned
        await (
            db.schema("journeys")
            .table("step_completions")
            .update({"points_earned": new_points})
            .eq("id", comp["id"])
            .execute()
        )

        # Update points_ledger entry linked to this completion
        await (
            db.schema("journeys")
            .table("points_ledger")
            .update({"amount": new_points})
            .eq("reference_id", comp["id"])
            .eq("reason", "step_completed")
            .execute()
        )

        updated += 1

    return updated
