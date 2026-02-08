from datetime import UTC, datetime
from uuid import UUID

from supabase import AsyncClient


async def get_active_enrollment(
    db: AsyncClient, user_id: UUID, journey_id: UUID
) -> dict | None:
    response = (
        await db.schema("journeys").table("enrollments")
        .select("*")
        .eq("user_id", str(user_id))
        .eq("journey_id", str(journey_id))
        .in_("status", ["active", "completed"])
        .execute()
    )

    return response.data[0] if response.data else None


async def create_enrollment(
    db: AsyncClient, user_id: UUID, journey_id: UUID
) -> dict:
    payload = {
        "user_id": str(user_id),
        "journey_id": str(journey_id),
        "status": "active",
        "current_step_index": 0,
    }

    response = await db.schema("journeys").table("enrollments").insert(payload).execute()
    return response.data[0]


async def get_enrollment_by_id(db: AsyncClient, enrollment_id: UUID) -> dict | None:
    response = (
        await db.schema("journeys").table("enrollments")
        .select("*")
        .eq("id", str(enrollment_id))
        .single()
        .execute()
    )
    return response.data


async def get_user_enrollments(
    db: AsyncClient, user_id: UUID, status: str | None = None
) -> list[dict]:
    query = db.schema("journeys").table("enrollments").select("*").eq("user_id", str(user_id))

    if status:
        query = query.eq("status", status)

    response = await query.order("started_at", desc=True).execute()
    return response.data or []


async def get_enrollment_with_progress(
    db: AsyncClient, enrollment_id: UUID
) -> dict | None:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        return None

    journey_id = enrollment["journey_id"]

    journey_response = (
        await db.schema("journeys").table("journeys")
        .select("id, title, slug, description, thumbnail_url")
        .eq("id", journey_id)
        .single()
        .execute()
    )
    journey = journey_response.data

    steps_response = (
        await db.schema("journeys").table("steps")
        .select("id, title, type, order_index")
        .eq("journey_id", journey_id)
        .order("order_index")
        .execute()
    )
    all_steps = steps_response.data or []

    completions_response = (
        await db.schema("journeys").table("step_completions")
        .select("step_id, completed_at, points_earned")
        .eq("enrollment_id", str(enrollment_id))
        .execute()
    )
    completions = {c["step_id"]: c for c in (completions_response.data or [])}

    steps_progress = []
    completed_count = 0
    current_step_index = enrollment.get("current_step_index", 0)

    for idx, step in enumerate(all_steps):
        step_id = step["id"]
        completion = completions.get(step_id)

        if completion:
            step_status = "completed"
            completed_count += 1
        elif idx <= current_step_index:
            step_status = "available"
        else:
            step_status = "locked"

        steps_progress.append(
            {
                "step_id": step_id,
                "title": step["title"],
                "type": step["type"],
                "order_index": step["order_index"],
                "status": step_status,
                "completed_at": completion["completed_at"] if completion else None,
                "points_earned": completion["points_earned"] if completion else 0,
            }
        )

    if journey:
        journey["total_steps"] = len(all_steps)

    return {
        **enrollment,
        "journey": journey,
        "steps_progress": steps_progress,
        "completed_steps": completed_count,
        "total_steps": len(all_steps),
    }


async def get_enrollment_step_progress(
    db: AsyncClient, enrollment_id: UUID
) -> list[dict]:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        return []

    journey_id = enrollment["journey_id"]

    steps_response = (
        await db.schema("journeys").table("steps")
        .select("id, title, type, order_index")
        .eq("journey_id", journey_id)
        .order("order_index")
        .execute()
    )
    all_steps = steps_response.data or []

    completions_response = (
        await db.schema("journeys").table("step_completions")
        .select("*")
        .eq("enrollment_id", str(enrollment_id))
        .execute()
    )
    completions = {c["step_id"]: c for c in (completions_response.data or [])}

    current_index = enrollment.get("current_step_index", 0)
    progress = []

    for idx, step in enumerate(all_steps):
        step_id = step["id"]
        completion = completions.get(step_id)

        if completion:
            step_status = "completed"
        elif idx <= current_index:
            step_status = "available"
        else:
            step_status = "locked"

        progress.append(
            {
                "step_id": step_id,
                "title": step["title"],
                "type": step["type"],
                "order_index": step["order_index"],
                "status": step_status,
                "completed_at": completion["completed_at"] if completion else None,
                "points_earned": completion["points_earned"] if completion else 0,
            }
        )

    return progress


async def can_complete_enrollment(
    db: AsyncClient, enrollment_id: UUID
) -> tuple[bool, str]:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        return False, "Inscripcion no encontrada."

    journey_id = enrollment["journey_id"]

    steps_response = (
        await db.schema("journeys").table("steps")
        .select("id", count="exact")
        .eq("journey_id", journey_id)
        .execute()
    )
    total_steps = steps_response.count or 0

    completions_response = (
        await db.schema("journeys").table("step_completions")
        .select("id", count="exact")
        .eq("enrollment_id", str(enrollment_id))
        .execute()
    )
    completed_steps = completions_response.count or 0

    if completed_steps < total_steps:
        return False, f"Faltan {total_steps - completed_steps} steps por completar."

    return True, "Todos los steps completados."


async def update_enrollment_status(
    db: AsyncClient, enrollment_id: UUID, new_status: str
) -> dict:
    update_data = {"status": new_status}

    if new_status == "completed":
        update_data["completed_at"] = datetime.now(UTC).isoformat()

    response = (
        await db.schema("journeys").table("enrollments")
        .update(update_data)
        .eq("id", str(enrollment_id))
        .execute()
    )

    return response.data[0] if response.data else {}


async def complete_step(
    db: AsyncClient,
    enrollment_id: UUID,
    step_id: UUID,
    metadata: dict | None = None,
    external_reference: str | None = None,
) -> dict:
    payload = {
        "enrollment_id": str(enrollment_id),
        "step_id": str(step_id),
        "points_earned": 0,
        "metadata": metadata or {},
    }
    if external_reference:
        payload["external_reference"] = external_reference

    response = await db.schema("journeys").table("step_completions").insert(payload).execute()
    return response.data[0] if response.data else {}


async def is_step_already_completed(
    db: AsyncClient, enrollment_id: UUID, step_id: UUID
) -> bool:
    response = (
        await db.schema("journeys").table("step_completions")
        .select("id")
        .eq("enrollment_id", str(enrollment_id))
        .eq("step_id", str(step_id))
        .execute()
    )
    return len(response.data) > 0 if response.data else False


async def verify_step_in_enrollment_journey(
    db: AsyncClient, enrollment_id: UUID, step_id: UUID
) -> bool:
    enrollment = await get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        return False

    journey_id = enrollment["journey_id"]

    response = (
        await db.schema("journeys").table("steps")
        .select("id")
        .eq("id", str(step_id))
        .eq("journey_id", journey_id)
        .execute()
    )
    return len(response.data) > 0 if response.data else False
