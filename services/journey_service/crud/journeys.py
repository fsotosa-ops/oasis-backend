from uuid import UUID

from services.journey_service.schemas.journeys import JourneyCreate, JourneyUpdate
from supabase import AsyncClient


# ---------------------------------------------------------------------------
# Read operations (for members)
# ---------------------------------------------------------------------------
async def get_journeys_for_org(
    db: AsyncClient,
    org_id: str,
    is_active: bool | None = True,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    # Get journey IDs assigned to this org via junction table
    jo_response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .select("journey_id")
        .eq("organization_id", org_id)
        .execute()
    )
    assigned_ids = [row["journey_id"] for row in (jo_response.data or [])]

    if not assigned_ids:
        return [], 0

    query = (
        db.schema("journeys").table("journeys")
        .select("*", count="exact")
        .in_("id", assigned_ids)
    )

    if is_active is not None:
        query = query.eq("is_active", is_active)

    response = (
        await query.order("created_at", desc=True)
        .range(skip, skip + limit - 1)
        .execute()
    )

    return response.data or [], response.count or 0


async def get_journey_by_id(db: AsyncClient, journey_id: UUID) -> dict | None:
    response = (
        await db.schema("journeys").table("journeys")
        .select("*")
        .eq("id", str(journey_id))
        .single()
        .execute()
    )
    return response.data


async def get_journey_with_steps(db: AsyncClient, journey_id: UUID) -> dict | None:
    journey_response = (
        await db.schema("journeys").table("journeys")
        .select("*")
        .eq("id", str(journey_id))
        .single()
        .execute()
    )

    if not journey_response.data:
        return None

    journey = journey_response.data

    steps_response = (
        await db.schema("journeys").table("steps")
        .select("*")
        .eq("journey_id", str(journey_id))
        .order("order_index")
        .execute()
    )

    journey["steps"] = steps_response.data or []
    return journey


async def get_steps_by_journey(db: AsyncClient, journey_id: UUID) -> list[dict]:
    response = (
        await db.schema("journeys").table("steps")
        .select("*")
        .eq("journey_id", str(journey_id))
        .order("order_index")
        .execute()
    )
    return response.data or []


async def verify_journey_belongs_to_org(
    db: AsyncClient,
    journey_id: UUID,
    org_id: str,
) -> bool:
    response = (
        await db.schema("journeys").table("journeys")
        .select("id")
        .eq("id", str(journey_id))
        .eq("organization_id", org_id)
        .execute()
    )
    return len(response.data) > 0 if response.data else False


async def verify_journey_accessible_by_org(
    db: AsyncClient,
    journey_id: UUID,
    org_id: str,
) -> bool:
    """Check if a journey is accessible by an org (owned OR assigned via junction table)."""
    response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .select("id")
        .eq("journey_id", str(journey_id))
        .eq("organization_id", org_id)
        .execute()
    )
    return len(response.data) > 0 if response.data else False


# ---------------------------------------------------------------------------
# Admin CRUD operations
# ---------------------------------------------------------------------------
async def create_journey(
    db: AsyncClient,
    org_id: str,
    journey: JourneyCreate,
) -> dict:
    payload = {
        "organization_id": org_id,
        "title": journey.title,
        "slug": journey.slug,
        "description": journey.description,
        "thumbnail_url": journey.thumbnail_url,
        "is_active": journey.is_active,
        "is_onboarding": journey.is_onboarding,
        "metadata": journey.metadata,
    }

    response = await db.schema("journeys").table("journeys").insert(payload).execute()
    created = response.data[0] if response.data else {}

    # Auto-assign to owner organization in junction table
    if created:
        await db.schema("journeys").table("journey_organizations").insert(
            {
                "journey_id": created["id"],
                "organization_id": org_id,
            }
        ).execute()

    return created


async def update_journey(
    db: AsyncClient,
    journey_id: UUID,
    journey: JourneyUpdate,
) -> dict:
    payload = {k: v for k, v in journey.model_dump().items() if v is not None}

    if not payload:
        response = (
            await db.schema("journeys").table("journeys")
            .select("*")
            .eq("id", str(journey_id))
            .single()
            .execute()
        )
        return response.data

    response = (
        await db.schema("journeys").table("journeys")
        .update(payload)
        .eq("id", str(journey_id))
        .execute()
    )
    return response.data[0] if response.data else {}


async def delete_journey(db: AsyncClient, journey_id: UUID) -> bool:
    response = (
        await db.schema("journeys").table("journeys").delete().eq("id", str(journey_id)).execute()
    )
    return len(response.data) > 0 if response.data else False


async def get_journey_admin(db: AsyncClient, journey_id: UUID) -> dict | None:
    journey_resp = (
        await db.schema("journeys").table("journeys")
        .select("*")
        .eq("id", str(journey_id))
        .single()
        .execute()
    )

    if not journey_resp.data:
        return None

    journey = journey_resp.data

    steps_resp = (
        await db.schema("journeys").table("steps")
        .select("id", count="exact")
        .eq("journey_id", str(journey_id))
        .execute()
    )
    journey["total_steps"] = steps_resp.count or 0

    enrollments_resp = (
        await db.schema("journeys").table("enrollments")
        .select("status")
        .eq("journey_id", str(journey_id))
        .execute()
    )

    enrollments = enrollments_resp.data or []
    journey["total_enrollments"] = len(enrollments)
    journey["active_enrollments"] = sum(
        1 for e in enrollments if e["status"] == "active"
    )
    journey["completed_enrollments"] = sum(
        1 for e in enrollments if e["status"] == "completed"
    )

    if journey["total_enrollments"] > 0:
        journey["completion_rate"] = round(
            (journey["completed_enrollments"] / journey["total_enrollments"]) * 100, 2
        )
    else:
        journey["completion_rate"] = 0.0

    return journey


async def list_journeys_admin(
    db: AsyncClient,
    org_id: str,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    # Get journey IDs assigned to this org via junction table
    jo_response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .select("journey_id")
        .eq("organization_id", org_id)
        .execute()
    )
    assigned_ids = [row["journey_id"] for row in (jo_response.data or [])]

    if not assigned_ids:
        return [], 0

    query = (
        db.schema("journeys").table("journeys")
        .select("*", count="exact")
        .in_("id", assigned_ids)
    )

    if is_active is not None:
        query = query.eq("is_active", is_active)

    response = (
        await query.order("created_at", desc=True)
        .range(skip, skip + limit - 1)
        .execute()
    )
    journeys = response.data or []
    total = response.count or 0

    for journey in journeys:
        steps_resp = (
            await db.schema("journeys").table("steps")
            .select("id", count="exact")
            .eq("journey_id", journey["id"])
            .execute()
        )
        journey["total_steps"] = steps_resp.count or 0

        enroll_resp = (
            await db.schema("journeys").table("enrollments")
            .select("status")
            .eq("journey_id", journey["id"])
            .execute()
        )
        enrollments = enroll_resp.data or []
        journey["total_enrollments"] = len(enrollments)
        journey["active_enrollments"] = sum(
            1 for e in enrollments if e["status"] == "active"
        )
        journey["completed_enrollments"] = sum(
            1 for e in enrollments if e["status"] == "completed"
        )

    return journeys, total


async def publish_journey(db: AsyncClient, journey_id: UUID) -> dict:
    response = (
        await db.schema("journeys").table("journeys")
        .update({"is_active": True})
        .eq("id", str(journey_id))
        .execute()
    )
    return response.data[0] if response.data else {}


async def archive_journey(db: AsyncClient, journey_id: UUID) -> dict:
    response = (
        await db.schema("journeys").table("journeys")
        .update({"is_active": False})
        .eq("id", str(journey_id))
        .execute()
    )
    return response.data[0] if response.data else {}
