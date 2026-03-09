import logging

from uuid import UUID

from common.cache.redis_client import cache_delete, cache_get_json, cache_set_json
from services.journey_service.schemas.journeys import JourneyCreate, JourneyUpdate
from supabase import AsyncClient

logger = logging.getLogger("oasis.journey.crud")

_JOURNEY_CACHE_TTL = 900  # 15 minutes


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
    # Only cache the default query (active, first page)
    use_cache = is_active is True and skip == 0 and limit == 50
    cache_key = f"org_journeys:{org_id}"

    if use_cache:
        cached = cache_get_json(cache_key)
        if cached is not None:
            logger.debug("CACHE_HIT org_journeys:%s", org_id)
            return cached.get("data", []), cached.get("count", 0)

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

    data = response.data or []
    count = response.count or 0

    if use_cache:
        cache_set_json(cache_key, {"data": data, "count": count}, _JOURNEY_CACHE_TTL)

    return data, count


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
    cache_key = f"journey:{journey_id}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        logger.debug("CACHE_HIT journey:%s", journey_id)
        return cached

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

    cache_set_json(cache_key, journey, _JOURNEY_CACHE_TTL)
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
        "category": journey.category,
        "is_active": journey.is_active,
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
        cache_delete(f"org_journeys:{org_id}")

    return created


async def update_journey(
    db: AsyncClient,
    journey_id: UUID,
    journey: JourneyUpdate,
) -> dict:
    payload = journey.model_dump(exclude_unset=True)
    payload.pop("is_onboarding", None)

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
    result = response.data[0] if response.data else {}

    # Invalidate caches
    cache_delete(f"journey:{journey_id}")
    if result.get("organization_id"):
        cache_delete(f"org_journeys:{result['organization_id']}")

    return result


async def delete_journey(db: AsyncClient, journey_id: UUID) -> bool:
    # Fetch org_id before deleting for cache invalidation
    pre = (
        await db.schema("journeys").table("journeys")
        .select("organization_id")
        .eq("id", str(journey_id))
        .maybe_single()
        .execute()
    )
    org_id = pre.data.get("organization_id") if pre.data else None

    response = (
        await db.schema("journeys").table("journeys").delete().eq("id", str(journey_id)).execute()
    )
    deleted = len(response.data) > 0 if response.data else False

    if deleted:
        cache_delete(f"journey:{journey_id}")
        if org_id:
            cache_delete(f"org_journeys:{org_id}")

    return deleted


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