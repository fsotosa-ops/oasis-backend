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

    NUEVA SEMÁNTICA (cambio de modelo del funnel):
    - La base de "inscritos" en cada (event, journey) son **todos los asistentes**
      del evento (filas en crm.event_attendances con status registered/attended),
      independientemente de su membresía en la org. Lo que cuenta es que asistieron.
    - El estado del funnel por usuario se determina cruzando con journeys.enrollments:
        completed   → enrollment.status='completed'
        active      → enrollment.status='active'
        not_started → sin enrollment, o enrollment con status pending/dropped
    - Los enrollments con event_id NULL quedan fuera del scope jerárquico (siguen
      en `unassigned_journeys` con la lógica legacy, ahí sí scoped a miembros activos).
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
    attendances_rows: list[dict] = []
    enrollments_by_key: dict[tuple[str, str, str], str] = {}

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

        # 5. Asistentes a los eventos (la nueva base del funnel — registered/attended).
        # Sin filtro de membresía: lo que cuenta es la asistencia, no el rol en la org.
        att_resp = (
            await db.schema("crm").table("event_attendances")
            .select("event_id, user_id, status")
            .in_("event_id", event_ids)
            .in_("status", ["registered", "attended"])
            .execute()
        )
        attendances_rows = att_resp.data or []

        # 6. Enrollments existentes (sólo para clasificar el estado del funnel).
        # Tampoco se filtra por miembros: si un asistente avanzó en el journey,
        # cuenta independientemente de su rol actual en la org.
        enr_resp = (
            await db.schema("journeys").table("enrollments")
            .select("journey_id, event_id, status, user_id")
            .in_("journey_id", journey_ids)
            .in_("event_id", event_ids)
            .execute()
        )
        for row in enr_resp.data or []:
            enrollments_by_key[
                (row["event_id"], row["journey_id"], row["user_id"])
            ] = row["status"]

    # Mapa evento → journeys asignadas
    event_journey_map: dict[str, list[str]] = {}
    for row in ej_rows:
        event_journey_map.setdefault(row["event_id"], []).append(row["journey_id"])

    # Mapa evento → asistentes (set de user_ids)
    attendees_by_event: dict[str, set[str]] = {}
    for row in attendances_rows:
        attendees_by_event.setdefault(row["event_id"], set()).add(row["user_id"])

    # Bucket de stats por (event_id, journey_id) — se construye desde asistentes × journeys
    stats: dict[tuple[str, str], dict[str, int]] = {}
    for ev_id, j_ids_in_event in event_journey_map.items():
        event_attendees = attendees_by_event.get(ev_id, set())
        for j_id in j_ids_in_event:
            bucket = {"total": 0, "active": 0, "completed": 0, "not_started": 0}
            for user_id in event_attendees:
                bucket["total"] += 1
                enr_status = enrollments_by_key.get((ev_id, j_id, user_id))
                if enr_status == "completed":
                    bucket["completed"] += 1
                elif enr_status == "active":
                    bucket["active"] += 1
                else:
                    # Sin enrollment, o pending/dropped → no iniciado
                    bucket["not_started"] += 1
            stats[(ev_id, j_id)] = bucket

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
                (ev_id, j_id),
                {"total": 0, "active": 0, "completed": 0, "not_started": 0},
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
                "not_started_enrollments": bucket["not_started"],
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
                # Lógica legacy (no hay evento que sirva de base, así que not_started=0).
                "not_started_enrollments": 0,
                "completion_rate": round(b["completed"] / t, 4) if t > 0 else 0.0,
            })

    # 7. Totales agregados — base = asistentes únicos en eventos con journeys
    unique_users: set[str] = set()
    total_potential = 0
    for ev_id, j_list in event_journey_map.items():
        ev_attendees = attendees_by_event.get(ev_id, set())
        unique_users.update(ev_attendees)
        total_potential += len(ev_attendees) * len(j_list)
    # unassigned: cae a la lógica legacy (cuento enrollments reales)
    for row in unassigned_enrollments_rows:
        unique_users.add(row["user_id"])

    return {
        "organization_id": org_id,
        "events": out_events,
        "total_members": total_members,
        # Mismo nombre, nueva semántica: asistentes únicos a eventos con journeys.
        "total_unique_enrolled_users": len(unique_users),
        # Mismo nombre, nueva semántica: asignaciones potenciales (asistentes × journeys/evento).
        "total_enrollments": total_potential,
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


async def list_journey_enrollees(
    db: AsyncClient,
    org_id: str,
    journey_id: str,
    event_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """
    Devuelve la lista de usuarios asociados a un journey en el contexto de un evento.

    NUEVA SEMÁNTICA (consistente con list_org_tracking):
    - La base son **todos los asistentes del evento** (registered/attended), sin
      filtrar por membresía. Lo que cuenta es la asistencia, no el rol en la org.
    - El estado del funnel se determina cruzando con journeys.enrollments en
      (journey_id, event_id, user_id):
        completed   → enrollment.status='completed'
        active      → enrollment.status='active'
        not_started → sin enrollment, o pending/dropped
    - Si event_id es None (drilldown desde unassigned_journeys) cae al modo
      legacy: la base son los enrollments reales filtrados a miembros activos.
    - El parámetro `status` filtra el resultado: 'not_started' | 'active' |
      'completed' | None (todos).
    """
    user_ids: list[str]
    enrollments_by_user: dict[str, dict] = {}
    registered_at_by_user: dict[str, str] = {}

    if event_id is not None:
        # 2a. Caso event_id presente: base = todos los asistentes del evento
        att_resp = (
            await db.schema("crm").table("event_attendances")
            .select("user_id, registered_at")
            .eq("event_id", event_id)
            .in_("status", ["registered", "attended"])
            .execute()
        )
        attendees = att_resp.data or []
        if not attendees:
            return []

        user_ids = [a["user_id"] for a in attendees]
        registered_at_by_user = {a["user_id"]: a["registered_at"] for a in attendees}

        # Enrollments existentes para esos usuarios en (journey, event)
        enr_resp = (
            await db.schema("journeys").table("enrollments")
            .select(
                "id, user_id, status, current_step_index, "
                "progress_percentage, started_at, completed_at"
            )
            .eq("journey_id", journey_id)
            .eq("event_id", event_id)
            .in_("user_id", user_ids)
            .execute()
        )
        enrollments_by_user = {e["user_id"]: e for e in (enr_resp.data or [])}
    else:
        # 2b. Caso unassigned (event_id=None): lógica legacy — base = enrollments reales
        # filtrados a miembros activos (no hay evento que sirva de base).
        members_resp = (
            await db.table("organization_members")
            .select("user_id")
            .eq("organization_id", org_id)
            .eq("status", "active")
            .execute()
        )
        member_user_ids = [row["user_id"] for row in (members_resp.data or [])]
        if not member_user_ids:
            return []

        enr_resp = (
            await db.schema("journeys").table("enrollments")
            .select(
                "id, user_id, status, current_step_index, "
                "progress_percentage, started_at, completed_at"
            )
            .eq("journey_id", journey_id)
            .in_("user_id", member_user_ids)
            .execute()
        )
        rows = enr_resp.data or []
        if not rows:
            return []
        user_ids = [e["user_id"] for e in rows]
        enrollments_by_user = {e["user_id"]: e for e in rows}

    # 3. Profiles para los user_ids resultantes
    profiles_resp = (
        await db.table("profiles")
        .select("id, full_name, email")
        .in_("id", user_ids)
        .execute()
    )
    profiles_by_id = {p["id"]: p for p in (profiles_resp.data or [])}

    # 3b. CRM contacts para datos enriquecidos
    contacts_by_id: dict[str, dict] = {}
    if user_ids:
        crm_resp = (
            await db.schema("crm").table("contacts")
            .select(
                "user_id, first_name, last_name, phone, company, "
                "country, state, city, birth_date, gender, "
                "education_level, occupation"
            )
            .in_("user_id", user_ids)
            .execute()
        )
        contacts_by_id = {c["user_id"]: c for c in (crm_resp.data or [])}

    # 4. Merge: por cada user, computar funnel state
    out: list[dict] = []
    for user_id in user_ids:
        e = enrollments_by_user.get(user_id)
        p = profiles_by_id.get(user_id, {})

        if e is None:
            funnel_status = "not_started"
            enrollment_id = None
            progress = 0.0
            current_step = 0
            started_at = registered_at_by_user.get(user_id)
            completed_at = None
        else:
            raw = e.get("status")
            funnel_status = (
                "completed" if raw == "completed"
                else "active" if raw == "active"
                else "not_started"
            )
            enrollment_id = e["id"]
            progress = e.get("progress_percentage") or 0.0
            current_step = e.get("current_step_index") or 0
            started_at = e.get("started_at")
            completed_at = e.get("completed_at")

        if status is not None and funnel_status != status:
            continue

        c = contacts_by_id.get(user_id, {})
        out.append({
            "user_id": user_id,
            "enrollment_id": enrollment_id,
            "full_name": p.get("full_name"),
            "email": p.get("email"),
            "status": funnel_status,
            "progress_percentage": progress,
            "current_step_index": current_step,
            "started_at": started_at,
            "completed_at": completed_at,
            "first_name": c.get("first_name"),
            "last_name": c.get("last_name"),
            "phone": c.get("phone"),
            "company": c.get("company"),
            "country": c.get("country"),
            "state": c.get("state"),
            "city": c.get("city"),
            "birth_date": c.get("birth_date"),
            "gender": c.get("gender"),
            "education_level": c.get("education_level"),
            "occupation": c.get("occupation"),
        })

    # Sort: completed > active > not_started; dentro del bucket por progress desc
    rank = {"completed": 0, "active": 1, "not_started": 2}
    out.sort(key=lambda r: (rank.get(r["status"], 3), -(r["progress_percentage"] or 0.0)))
    return out


async def list_event_enrollees(
    db: AsyncClient,
    org_id: str,
    event_id: str,
    status: str | None = None,
) -> list[dict]:
    """Enrollees deduplicados por usuario para TODOS los journeys de un evento.

    Un usuario en múltiples journeys → 1 fila con journeys concatenados
    y el mejor status/progreso. Compatible con gestores de campañas
    (Brevo, Mailchimp) que requieren 1 fila por contacto.
    """
    # 1. Journeys asignados al evento Y a la org
    jo_resp = (
        await db.schema("journeys").table("journey_organizations")
        .select("journey_id")
        .eq("organization_id", org_id)
        .execute()
    )
    org_journey_ids = {r["journey_id"] for r in (jo_resp.data or [])}

    ev_resp = (
        await db.schema("crm").table("event_journeys")
        .select("journey_id")
        .eq("event_id", event_id)
        .execute()
    )
    event_journey_ids = [
        r["journey_id"]
        for r in (ev_resp.data or [])
        if r["journey_id"] in org_journey_ids
    ]
    if not event_journey_ids:
        return []

    # Títulos
    j_resp = (
        await db.schema("journeys").table("journeys")
        .select("id, title")
        .in_("id", event_journey_ids)
        .execute()
    )
    title_by_id = {j["id"]: j["title"] for j in (j_resp.data or [])}

    # 2. Enrollees por journey (reutiliza función existente)
    all_rows: list[tuple[str, dict]] = []
    for jid in event_journey_ids:
        rows = await list_journey_enrollees(
            db, org_id, jid, event_id=event_id, status=None,
        )
        jtitle = title_by_id.get(jid, "")
        for r in rows:
            all_rows.append((jtitle, r))

    # 3. Agrupar por user_id: acumular datos por journey
    status_labels = {"completed": "Completado", "active": "En progreso", "not_started": "No iniciado"}
    user_map: dict[str, dict] = {}

    for jtitle, row in all_rows:
        uid = row["user_id"]
        pct = int(row.get("progress_percentage") or 0)
        st = row.get("status", "not_started")
        started = (row.get("started_at") or "")[:10] if row.get("started_at") else ""
        completed = (row.get("completed_at") or "")[:10] if row.get("completed_at") else ""

        if uid not in user_map:
            # Copiar datos base del usuario (profile + CRM) del primer row
            user_map[uid] = {
                "user_id": uid,
                "full_name": row.get("full_name"),
                "email": row.get("email"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "phone": row.get("phone"),
                "company": row.get("company"),
                "country": row.get("country"),
                "state": row.get("state"),
                "city": row.get("city"),
                "birth_date": row.get("birth_date"),
                "gender": row.get("gender"),
                "education_level": row.get("education_level"),
                "occupation": row.get("occupation"),
                # Listas para concatenar por journey
                "_journeys": [jtitle],
                "_statuses": [status_labels.get(st, st)],
                "_progresses": [str(pct)],
                "_started": [started],
                "_completed": [completed],
            }
        else:
            existing = user_map[uid]
            existing["_journeys"].append(jtitle)
            existing["_statuses"].append(status_labels.get(st, st))
            existing["_progresses"].append(str(pct))
            existing["_started"].append(started)
            existing["_completed"].append(completed)

    # 4. Formatear salida — concatenar valores por journey
    status_rank = {"Completado": 0, "En progreso": 1, "No iniciado": 2}
    out: list[dict] = []
    for u in user_map.values():
        u["journeys"] = ", ".join(dict.fromkeys(u.pop("_journeys")))
        statuses = u.pop("_statuses")
        progresses = u.pop("_progresses")
        started_list = u.pop("_started")
        completed_list = u.pop("_completed")

        u["status"] = ", ".join(statuses)
        u["progress_percentage"] = ", ".join(progresses)
        u["started_at"] = ", ".join(s or "-" for s in started_list)
        u["completed_at"] = ", ".join(s or "-" for s in completed_list)

        # Filtro por status si se pidió
        if status:
            status_label = status_labels.get(status, status)
            if status_label not in statuses:
                continue

        # Ordenar por mejor status del usuario
        best_rank = min(status_rank.get(s, 3) for s in statuses)
        best_pct = max(int(p) for p in progresses)
        u["_sort"] = (best_rank, -best_pct)

        out.append(u)

    out.sort(key=lambda r: r.pop("_sort"))
    return out