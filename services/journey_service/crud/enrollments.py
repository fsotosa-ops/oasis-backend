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
    enrollments = response.data or []

    if not enrollments:
        return []

    # Fetch organization_id for each journey
    journey_ids = list({e["journey_id"] for e in enrollments})
    journeys_response = (
        await db.schema("journeys").table("journeys")
        .select("id, organization_id")
        .in_("id", journey_ids)
        .execute()
    )
    org_map = {j["id"]: j["organization_id"] for j in (journeys_response.data or [])}

    for e in enrollments:
        e["organization_id"] = org_map.get(e["journey_id"])

    return enrollments


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


async def get_step_by_id(db: AsyncClient, step_id: UUID) -> dict | None:
    response = (
        await db.schema("journeys").table("steps")
        .select("id, type, config, gamification_rules")
        .eq("id", str(step_id))
        .single()
        .execute()
    )
    return response.data


def _build_enriched_metadata(
    step: dict,
    client_metadata: dict | None,
    external_reference: str | None,
    service_data: dict | None,
) -> dict:
    """Build contextual metadata based on step type and config."""
    from datetime import datetime, UTC

    step_type = step.get("type", "")
    config = step.get("config") or {}
    now = datetime.now(UTC).isoformat()

    enriched: dict = {"step_type": step_type, "completed_at": now}

    # Extract service info from step config
    source_url = config.get("resource") or config.get("source_url") or config.get("url")

    if step_type == "survey":
        enriched["service"] = "typeform"
        form_id = config.get("typeform_id") or config.get("form_id")
        if form_id:
            enriched["form_id"] = form_id
        if external_reference:
            enriched["response_id"] = external_reference

    elif step_type == "content_view":
        if source_url:
            enriched["source_url"] = source_url
            if "youtube" in str(source_url):
                enriched["service"] = "youtube"
            elif "vimeo" in str(source_url):
                enriched["service"] = "vimeo"
            else:
                enriched["service"] = "video"

    elif step_type == "resource_consumption":
        if source_url:
            enriched["source_url"] = source_url
            if ".pdf" in str(source_url).lower():
                enriched["service"] = "pdf"
            elif "docs.google" in str(source_url) or "slides.google" in str(source_url):
                enriched["service"] = "google_slides"
            else:
                enriched["service"] = "resource"

    elif step_type == "milestone":
        if source_url:
            enriched["source_url"] = source_url
            if "kahoot" in str(source_url):
                enriched["service"] = "kahoot"
            else:
                enriched["service"] = "milestone"

    elif step_type == "event_attendance":
        enriched["service"] = "event"

    elif step_type == "social_interaction":
        enriched["service"] = "social"

    # Merge client-provided metadata and service_data
    if client_metadata:
        enriched.update(client_metadata)
    if service_data:
        enriched["service_data"] = service_data

    return enriched


async def complete_step(
    db: AsyncClient,
    enrollment_id: UUID,
    step_id: UUID,
    metadata: dict | None = None,
    external_reference: str | None = None,
    service_data: dict | None = None,
) -> dict:
    # Fetch step to enrich metadata
    step = await get_step_by_id(db, step_id)
    enriched_metadata = (
        _build_enriched_metadata(step, metadata, external_reference, service_data)
        if step
        else metadata or {}
    )

    payload = {
        "enrollment_id": str(enrollment_id),
        "step_id": str(step_id),
        "points_earned": 0,
        "metadata": enriched_metadata,
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
