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
            journey["completed_enrollments"] / journey["total_enrollments"], 4
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

    # Scope enrollment counts to users that belong to this org so that the
    # numbers shown in the UI ("Inscritos" / "Completados") reflect the org
    # being viewed instead of the journey's global reach across all orgs it
    # is assigned to.
    members_resp = (
        await db.table("organization_members")
        .select("user_id")
        .eq("organization_id", org_id)
        .eq("status", "active")
        .execute()
    )
    member_user_ids = [row["user_id"] for row in (members_resp.data or [])]

    for journey in journeys:
        steps_resp = (
            await db.schema("journeys").table("steps")
            .select("id", count="exact")
            .eq("journey_id", journey["id"])
            .execute()
        )
        journey["total_steps"] = steps_resp.count or 0

        if member_user_ids:
            enroll_resp = (
                await db.schema("journeys").table("enrollments")
                .select("status")
                .eq("journey_id", journey["id"])
                .in_("user_id", member_user_ids)
                .execute()
            )
            enrollments = enroll_resp.data or []
        else:
            enrollments = []

        journey["total_enrollments"] = len(enrollments)
        journey["active_enrollments"] = sum(
            1 for e in enrollments if e["status"] == "active"
        )
        journey["completed_enrollments"] = sum(
            1 for e in enrollments if e["status"] == "completed"
        )
        journey["completion_rate"] = (
            round(
                journey["completed_enrollments"] / journey["total_enrollments"], 4
            )
            if journey["total_enrollments"] > 0
            else 0.0
        )

    return journeys, total


async def list_org_tracking(db: AsyncClient, org_id: str) -> dict:
    """
    Devuelve la jerarquía Org → Eventos → Journeys con stats por (event_id, journey_id).

    - Lee eventos desde crm.org_events para la org dada.
    - Resuelve la asignación de journeys via crm.event_journeys.
    - Cuenta enrollments scoped por (journey_id, event_id) — los enrollments con
      event_id NULL quedan excluidos a propósito (no pertenecen a un evento del
      tracking jerárquico).
    - completion_rate se devuelve como decimal 0-1 (consistente con el resto del backend).
    - Los enrollments se filtran adicionalmente a los miembros activos de la org para
      que las cifras reflejen solo a los usuarios actualmente vinculados.
    """
    # 0. Miembros activos de la org (para scoping y para el header del UI)
    members_resp = (
        await db.table("organization_members")
        .select("user_id")
        .eq("organization_id", org_id)
        .eq("status", "active")
        .execute()
    )
    member_user_ids = [row["user_id"] for row in (members_resp.data or [])]
    total_members = len(member_user_ids)

    # 1. Eventos de la org
    events_resp = (
        await db.schema("crm").table("org_events")
        .select("id, name, slug, status, start_date, end_date, location")
        .eq("organization_id", org_id)
        .order("start_date", desc=True)
        .execute()
    )
    events = events_resp.data or []
    event_ids = [e["id"] for e in events]

    ej_rows: list[dict] = []
    journey_ids: list[str] = []
    journeys_meta: dict[str, dict] = {}
    step_counts: dict[str, int] = {}
    enrollments_rows: list[dict] = []

    if event_ids:
        # 2. Asignaciones evento ↔ journey
        ej_resp = (
            await db.schema("crm").table("event_journeys")
            .select("event_id, journey_id")
            .in_("event_id", event_ids)
            .execute()
        )
        ej_rows = ej_resp.data or []
        journey_ids = list({row["journey_id"] for row in ej_rows})

    if journey_ids:
        # 3. Metadata de journeys
        jm_resp = (
            await db.schema("journeys").table("journeys")
            .select("id, title, slug, category, is_active")
            .in_("id", journey_ids)
            .execute()
        )
        for j in jm_resp.data or []:
            journeys_meta[j["id"]] = j

        # 4. Conteo de steps por journey
        steps_resp = (
            await db.schema("journeys").table("steps")
            .select("journey_id")
            .in_("journey_id", journey_ids)
            .execute()
        )
        for s in steps_resp.data or []:
            step_counts[s["journey_id"]] = step_counts.get(s["journey_id"], 0) + 1

        # 5. Enrollments scoped a (journey_id, event_id) y a miembros activos
        if member_user_ids:
            enr_resp = (
                await db.schema("journeys").table("enrollments")
                .select("journey_id, event_id, status, user_id")
                .in_("journey_id", journey_ids)
                .in_("event_id", event_ids)
                .in_("user_id", member_user_ids)
                .execute()
            )
            enrollments_rows = enr_resp.data or []

    # Bucket de stats por (event_id, journey_id)
    stats: dict[tuple[str, str], dict[str, int]] = {}
    for row in enrollments_rows:
        key = (row["event_id"], row["journey_id"])
        bucket = stats.setdefault(key, {"total": 0, "active": 0, "completed": 0})
        bucket["total"] += 1
        if row["status"] == "active":
            bucket["active"] += 1
        elif row["status"] == "completed":
            bucket["completed"] += 1

    # Mapa evento → journeys asignadas
    event_journey_map: dict[str, list[str]] = {}
    for row in ej_rows:
        event_journey_map.setdefault(row["event_id"], []).append(row["journey_id"])

    # Ensamblar respuesta
    out_events: list[dict] = []
    for ev in events:
        ev_id = ev["id"]
        tracked_journeys: list[dict] = []
        for j_id in event_journey_map.get(ev_id, []):
            meta = journeys_meta.get(j_id)
            if not meta:
                continue
            bucket = stats.get(
                (ev_id, j_id), {"total": 0, "active": 0, "completed": 0}
            )
            total = bucket["total"]
            tracked_journeys.append({
                "id": meta["id"],
                "title": meta["title"],
                "slug": meta["slug"],
                "category": meta.get("category"),
                "is_active": meta.get("is_active", False),
                "total_steps": step_counts.get(j_id, 0),
                "total_enrollments": total,
                "active_enrollments": bucket["active"],
                "completed_enrollments": bucket["completed"],
                "completion_rate": (
                    round(bucket["completed"] / total, 4) if total > 0 else 0.0
                ),
            })
        out_events.append({
            "event_id": ev_id,
            "event_name": ev["name"],
            "event_slug": ev["slug"],
            "event_status": ev["status"],
            "start_date": ev.get("start_date"),
            "end_date": ev.get("end_date"),
            "location": ev.get("location"),
            "journeys": tracked_journeys,
        })

    # 6. Journeys asignados a la org pero no a ningún evento (no aparecerían en
    # la vista jerárquica). Se cuentan también scoped a miembros activos.
    all_assigned_resp = (
        await db.schema("journeys").table("journey_organizations")
        .select("journey_id")
        .eq("organization_id", org_id)
        .execute()
    )
    all_assigned_ids = {row["journey_id"] for row in (all_assigned_resp.data or [])}
    unassigned_ids = list(all_assigned_ids - set(journey_ids))

    unassigned_journeys: list[dict] = []
    unassigned_enrollments_rows: list[dict] = []
    if unassigned_ids:
        um_resp = (
            await db.schema("journeys").table("journeys")
            .select("id, title, slug, category, is_active")
            .in_("id", unassigned_ids)
            .execute()
        )
        us_resp = (
            await db.schema("journeys").table("steps")
            .select("journey_id")
            .in_("journey_id", unassigned_ids)
            .execute()
        )
        if member_user_ids:
            ue_resp = (
                await db.schema("journeys").table("enrollments")
                .select("journey_id, status, user_id")
                .in_("journey_id", unassigned_ids)
                .in_("user_id", member_user_ids)
                .execute()
            )
            unassigned_enrollments_rows = ue_resp.data or []

        u_step_counts: dict[str, int] = {}
        for s in us_resp.data or []:
            u_step_counts[s["journey_id"]] = u_step_counts.get(s["journey_id"], 0) + 1

        u_stats: dict[str, dict[str, int]] = {}
        for row in unassigned_enrollments_rows:
            b = u_stats.setdefault(
                row["journey_id"], {"total": 0, "active": 0, "completed": 0}
            )
            b["total"] += 1
            if row["status"] == "active":
                b["active"] += 1
            elif row["status"] == "completed":
                b["completed"] += 1

        for j in um_resp.data or []:
            b = u_stats.get(j["id"], {"total": 0, "active": 0, "completed": 0})
            t = b["total"]
            unassigned_journeys.append({
                "id": j["id"],
                "title": j["title"],
                "slug": j["slug"],
                "category": j.get("category"),
                "is_active": j.get("is_active", False),
                "total_steps": u_step_counts.get(j["id"], 0),
                "total_enrollments": t,
                "active_enrollments": b["active"],
                "completed_enrollments": b["completed"],
                "completion_rate": round(b["completed"] / t, 4) if t > 0 else 0.0,
            })

    # 7. Totales agregados (filas vs usuarios únicos)
    unique_users: set[str] = set()
    total_enrollments_count = 0
    for row in enrollments_rows:
        unique_users.add(row["user_id"])
        total_enrollments_count += 1
    for row in unassigned_enrollments_rows:
        unique_users.add(row["user_id"])
        total_enrollments_count += 1

    return {
        "organization_id": org_id,
        "events": out_events,
        "total_members": total_members,
        "total_unique_enrolled_users": len(unique_users),
        "total_enrollments": total_enrollments_count,
        "unassigned_journeys": unassigned_journeys,
    }


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