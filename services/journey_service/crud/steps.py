from uuid import UUID

from services.journey_service.schemas.journeys import StepCreate, StepUpdate, clean_config_for_type
from supabase import AsyncClient


async def get_next_step_index(db: AsyncClient, journey_id: UUID) -> int:
    response = (
        await db.schema("journeys").table("steps")
        .select("order_index")
        .eq("journey_id", str(journey_id))
        .order("order_index", desc=True)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]["order_index"] + 1
    return 0


async def create_step(
    db: AsyncClient,
    journey_id: UUID,
    step: StepCreate,
) -> dict:
    order_index = step.order_index
    if order_index is None:
        order_index = await get_next_step_index(db, journey_id)

    payload = {
        "journey_id": str(journey_id),
        "title": step.title,
        "type": step.type,
        "order_index": order_index,
        "config": clean_config_for_type(step.type, step.config),
        "gamification_rules": step.gamification_rules.model_dump(),
    }

    response = await db.schema("journeys").table("steps").insert(payload).execute()
    return response.data[0] if response.data else {}


async def update_step(
    db: AsyncClient,
    step_id: UUID,
    step: StepUpdate,
) -> dict:
    payload = {}

    if step.title is not None:
        payload["title"] = step.title
    if step.type is not None:
        payload["type"] = step.type
    if step.config is not None:
        payload["config"] = step.config
    if step.gamification_rules is not None:
        payload["gamification_rules"] = step.gamification_rules.model_dump()

    if not payload:
        response = (
            await db.schema("journeys").table("steps")
            .select("*")
            .eq("id", str(step_id))
            .single()
            .execute()
        )
        return response.data

    # Clean config against the step type when config or type is being updated
    if "config" in payload or "type" in payload:
        # Determine effective type: use incoming type, or fetch current from DB
        effective_type = payload.get("type")
        if not effective_type:
            current = (
                await db.schema("journeys").table("steps")
                .select("type")
                .eq("id", str(step_id))
                .single()
                .execute()
            )
            effective_type = current.data["type"] if current.data else None

        if effective_type and "config" in payload:
            payload["config"] = clean_config_for_type(effective_type, payload["config"])

    response = (
        await db.schema("journeys").table("steps")
        .update(payload)
        .eq("id", str(step_id))
        .execute()
    )
    return response.data[0] if response.data else {}


async def delete_step(db: AsyncClient, step_id: UUID) -> bool:
    response = (
        await db.schema("journeys").table("steps").delete().eq("id", str(step_id)).execute()
    )
    return len(response.data) > 0 if response.data else False


async def list_steps(db: AsyncClient, journey_id: UUID) -> list[dict]:
    response = (
        await db.schema("journeys").table("steps")
        .select("*")
        .eq("journey_id", str(journey_id))
        .order("order_index")
        .execute()
    )

    steps = response.data or []

    for step in steps:
        completions_resp = (
            await db.schema("journeys").table("step_completions")
            .select("points_earned")
            .eq("step_id", step["id"])
            .execute()
        )
        completions = completions_resp.data or []
        step["total_completions"] = len(completions)

        if completions:
            total_points = sum(c["points_earned"] for c in completions)
            step["average_points"] = round(total_points / len(completions), 2)
        else:
            step["average_points"] = 0.0

    return steps


async def reorder_steps(
    db: AsyncClient,
    journey_id: UUID,
    step_orders: list[dict],
) -> list[dict]:
    for item in step_orders:
        await (
            db.schema("journeys").table("steps")
            .update({"order_index": item["new_index"]})
            .eq("id", str(item["step_id"]))
            .eq("journey_id", str(journey_id))
            .execute()
        )

    return await list_steps(db, journey_id)


async def verify_step_belongs_to_org(
    db: AsyncClient,
    step_id: UUID,
    org_id: str,
) -> bool:
    step_resp = (
        await db.schema("journeys").table("steps")
        .select("journey_id")
        .eq("id", str(step_id))
        .single()
        .execute()
    )

    if not step_resp.data:
        return False

    journey_id = step_resp.data["journey_id"]

    from services.journey_service.crud.journeys import verify_journey_belongs_to_org

    return await verify_journey_belongs_to_org(db, journey_id, org_id)
