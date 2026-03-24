import csv
import io
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from common.auth.security import CurrentUser
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.crm_service.crud import contacts as crud_contacts
from services.crm_service.crud import notes as crud_notes
from services.crm_service.crud import tasks as crud_tasks
from services.crm_service.dependencies import (
    CrmContext,
    CrmGlobalReadAccess,
    CrmGlobalWriteAccess,
    CrmReadAccess,
    CrmWriteAccess,
)
from services.crm_service.schemas.contacts import (
    AssignEventRequest,
    AssignEventResponse,
    ContactEventParticipation,
    ContactResponse,
    ContactUpdate,
    PaginatedContactsResponse,
)
from services.crm_service.schemas.notes import NoteCreate, NoteResponse
from services.crm_service.schemas.tasks import TaskCreate, TaskResponse
from services.gamification_service.crud import config as gamif_config_crud
from services.journey_service.crud import steps as journey_steps_crud
from services.journey_service.crud.enrollments import (
    complete_step as complete_journey_step,
    create_enrollment,
    get_active_enrollment,
    is_step_already_completed,
)
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# Campos que se consideran para calcular si el perfil está "completo"
_COMPLETION_FIELDS = ("phone", "birth_date", "gender", "education_level", "occupation", "company", "city")
# Número mínimo de campos requeridos para considerar el perfil completo
_COMPLETION_THRESHOLD = 5


async def _try_award_profile_completion_points(db: AsyncClient, user_id: str, contact: dict) -> None:
    """Marca el step de 'Completar Perfil' en el Journey de Onboarding cuando el perfil
    supera el umbral de completitud. Si no hay Journey configurado, no hace nada
    (los puntos vienen del Journey trigger al completar el step manualmente).

    Flujo:
    1. Verifica que el perfil supere el umbral de campos rellenos.
    2. Busca la org del usuario.
    3. Lee gamification_config para obtener profile_completion_journey_id y profile_completion_step_id.
    4. Si están configurados:
       a. Busca o crea un enrollment activo en el Journey de Onboarding.
       b. Si el step ya está completado → skip (idempotente).
       c. Completa el step → el trigger SQL maneja puntos, ledger y rewards.
    5. Si NO están configurados → log y return (no hacer nada, evitar doble conteo).
    """
    # 1. Verificar si el perfil está completo
    filled = sum(1 for f in _COMPLETION_FIELDS if contact.get(f))
    logger.info("profile_completion: user=%s filled=%d/%d fields=%s", user_id, filled, _COMPLETION_THRESHOLD,
                {f: bool(contact.get(f)) for f in _COMPLETION_FIELDS})
    if filled < _COMPLETION_THRESHOLD:
        logger.info("profile_completion: user=%s threshold not met (%d < %d)", user_id, filled, _COMPLETION_THRESHOLD)
        return

    # 2. Buscar la organización del usuario
    membership = (
        await db.table("organization_members")
        .select("organization_id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("joined_at")
        .limit(1)
        .execute()
    )
    if not membership.data:
        logger.warning("profile_completion: user=%s has no organization membership, skipping", user_id)
        return
    org_id_str = membership.data[0]["organization_id"]
    org_id = UUID(org_id_str)

    # 3. Leer config de gamificación para este org
    config = await gamif_config_crud.get_config(db, org_id)
    journey_id_str = (config or {}).get("profile_completion_journey_id")
    step_id_str = (config or {}).get("profile_completion_step_id")

    if not journey_id_str or not step_id_str:
        logger.warning(
            "profile_completion: user=%s no onboarding journey/step configured for org=%s — "
            "configure profile_completion_journey_id and profile_completion_step_id in gamification_config",
            user_id, org_id_str,
        )
        return

    # 4. Usar el sistema de Journeys (fuente única de verdad para puntos/rewards)
    user_uuid = UUID(user_id)
    journey_id = UUID(journey_id_str)
    step_id = UUID(step_id_str)

    # a. Obtener o crear enrollment en el Journey de Onboarding
    enrollment = await get_active_enrollment(db, user_uuid, journey_id)
    if not enrollment:
        enrollment = await create_enrollment(db, user_uuid, journey_id)
        logger.info("profile_completion: user=%s enrolled in onboarding journey=%s", user_id, journey_id_str)

    enrollment_id = UUID(enrollment["id"])

    # b. Verificar si el step ya fue completado (idempotente)
    if await is_step_already_completed(db, enrollment_id, step_id):
        logger.info(
            "profile_completion: user=%s step=%s already completed — skipping",
            user_id, step_id_str,
        )
        return

    # c. Completar el step — el trigger SQL crea user_activities + points_ledger + rewards
    await complete_journey_step(
        db,
        enrollment_id,
        step_id,
        metadata={"trigger": "profile_completion", "fields_filled": filled},
    )
    logger.info(
        "profile_completion: user=%s completed step=%s in journey=%s (%d fields filled)",
        user_id, step_id_str, journey_id_str, filled,
    )

async def _try_complete_profile_field_steps(
    db: AsyncClient, user_id: str, contact: dict, updated_fields: set[str]
) -> None:
    """Auto-completa steps de tipo profile_field cuyas field_names ya están todas llenas,
    pero solo si al menos uno de sus campos fue actualizado en esta petición.

    Flujo:
    1. Busca la org del usuario.
    2. Lee gamification_config para obtener profile_completion_journey_id.
    3. Obtiene todos los steps de ese journey.
    4. Para cada step de tipo profile_field: si al menos uno de sus field_names fue actualizado
       Y todos sus field_names tienen valor en el contacto → marca el step como completado.
    """
    # 1. Buscar organización
    membership = (
        await db.table("organization_members")
        .select("organization_id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("joined_at")
        .limit(1)
        .execute()
    )
    if not membership.data:
        return
    org_id_str = membership.data[0]["organization_id"]
    org_id = UUID(org_id_str)

    # 2. Leer config de gamificación
    config = await gamif_config_crud.get_config(db, org_id)
    journey_id_str = (config or {}).get("profile_completion_journey_id")
    if not journey_id_str:
        return

    journey_id = UUID(journey_id_str)
    user_uuid = UUID(user_id)

    # 3. Obtener steps del journey de onboarding
    steps = await journey_steps_crud.list_steps(db, journey_id)
    profile_field_steps = [s for s in steps if s.get("type") == "profile_field"]
    if not profile_field_steps:
        return

    # 4. Obtener o crear enrollment
    enrollment = await get_active_enrollment(db, user_uuid, journey_id)
    if not enrollment:
        enrollment = await create_enrollment(db, user_uuid, journey_id)
        logger.info("profile_field: user=%s enrolled in onboarding journey=%s", user_id, journey_id_str)

    enrollment_id = UUID(enrollment["id"])

    # 5. Para cada step profile_field: verificar si todos sus campos están llenos
    for step in profile_field_steps:
        step_id = UUID(step["id"])
        step_config = step.get("config") or {}
        field_names: list[str] = step_config.get("field_names", [])

        if not field_names:
            continue

        # Solo auto-completar si al menos uno de los campos del step fue actualizado
        if not updated_fields.intersection(field_names):
            continue

        all_filled = all(bool(contact.get(f)) for f in field_names)
        if not all_filled:
            continue

        if await is_step_already_completed(db, enrollment_id, step_id):
            continue

        await complete_journey_step(
            db,
            enrollment_id,
            step_id,
            metadata={"trigger": "profile_field_auto_complete", "fields": field_names},
        )
        logger.info(
            "profile_field: user=%s auto-completed step=%s fields=%s",
            user_id, str(step_id), field_names,
        )


router = APIRouter()


@router.get("/", response_model=PaginatedContactsResponse)
async def list_contacts(
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: CrmContext = Depends(CrmGlobalReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    contacts, count = await crud_contacts.get_contacts(
        db=db,
        organization_id=ctx.organization_id,
        search=search,
        limit=limit,
        offset=skip,
    )
    return {"contacts": contacts, "count": count}


@router.get("/me", response_model=ContactResponse)
async def get_my_contact(
    user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Permite a cualquier usuario autenticado consultar su propio contacto CRM."""
    contact = await crud_contacts.get_contact_by_id(db, str(user.id))
    if not contact:
        raise NotFoundError("Contact")
    return contact


COUNTRY_NAMES: dict[str, str] = {
    "CL": "Chile",
    "AR": "Argentina",
    "CO": "Colombia",
    "MX": "México",
    "PE": "Perú",
    "BR": "Brasil",
    "EC": "Ecuador",
    "BO": "Bolivia",
    "UY": "Uruguay",
    "PY": "Paraguay",
    "VE": "Venezuela",
    "CR": "Costa Rica",
    "PA": "Panamá",
    "GT": "Guatemala",
    "HN": "Honduras",
    "SV": "El Salvador",
    "NI": "Nicaragua",
    "DO": "República Dominicana",
    "CU": "Cuba",
    "PR": "Puerto Rico",
    "US": "Estados Unidos",
    "ES": "España",
}

CSV_COLUMNS = [
    "USER_ID", "EMAIL", "FIRSTNAME", "LASTNAME", "PHONE", "COMPANY",
    "COUNTRY", "STATE", "CITY", "BIRTH_DATE", "GENDER", "EDUCATION_LEVEL",
    "OCCUPATION", "CRM_STATUS", "OASIS_SCORE", "ORGANIZATIONS",
    "TOTAL_EVENTS_ATTENDED", "LAST_EVENT_NAME", "LAST_EVENT_DATE",
    "TOTAL_POINTS", "CURRENT_LEVEL", "ACTIVE_JOURNEYS", "PENDING_JOURNEYS",
    "COMPLETED_JOURNEYS", "LAST_SEEN_AT", "CREATED_AT",
]

# Map RPC result keys → CSV column order
_RPC_KEYS = [
    "user_id", "email", "first_name", "last_name", "phone", "company",
    "country", "state", "city", "birth_date", "gender", "education_level",
    "occupation", "crm_status", "oasis_score", "organizations",
    "total_events_attended", "last_event_name", "last_event_date",
    "total_points", "current_level", "active_journeys", "pending_journeys",
    "completed_journeys", "last_seen_at", "created_at",
]


@router.get("/export/csv", summary="Exportar contactos como CSV para Brevo")
async def export_contacts_csv(
    organization_ids: str | None = Query(None, description="Comma-separated org UUIDs"),
    created_from: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    created_to: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    ctx: CrmContext = Depends(CrmGlobalReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    # Build org IDs array
    org_ids_list: list[str] | None = None
    if organization_ids:
        org_ids_list = [s.strip() for s in organization_ids.split(",") if s.strip()]
    elif ctx.organization_id:
        # Non-superadmin: always scoped to their org
        org_ids_list = [str(ctx.organization_id)]

    # PostgREST requires ALL params to be present to match the function signature
    params: dict = {
        "p_organization_ids": org_ids_list,
        "p_created_from": f"{created_from}T00:00:00Z" if created_from else None,
        "p_created_to": f"{created_to}T23:59:59Z" if created_to else None,
    }

    result = await db.rpc("export_contacts_for_brevo", params).execute()
    rows = result.data or []

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)

    for row in rows:
        values = [row.get(k, "") or "" for k in _RPC_KEYS]
        # Resolve country ISO code → name
        country_val = values[6]
        if country_val and len(country_val) == 2:
            values[6] = COUNTRY_NAMES.get(country_val.upper(), country_val)
        writer.writerow(values)

    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"contacts_brevo_{now}.csv"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    ctx: CrmContext = Depends(CrmGlobalReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    contact = await crud_contacts.get_contact_by_id(db, str(contact_id))
    if not contact:
        raise NotFoundError("Contact")

    # Si hay org_id, verificar que el contacto pertenece a esa org
    if ctx.organization_id:
        belongs = await crud_contacts.contact_belongs_to_org(
            db, str(contact_id), ctx.organization_id
        )
        if not belongs:
            raise ForbiddenError("El contacto no pertenece a tu organización")

    return contact


@router.patch("/me", response_model=ContactResponse)
async def update_my_contact(
    data: ContactUpdate,
    user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Permite a cualquier usuario autenticado actualizar su propio contacto CRM.
    Usa upsert: crea el registro si no existe todavía.
    """
    user_id = str(user.id)
    update_data = data.model_dump(exclude_unset=True, mode="json")

    if not update_data:
        # Nada que actualizar — devolver contacto existente sin tocar la BD
        existing = await crud_contacts.get_contact_by_id(db, user_id)
        if not existing:
            raise NotFoundError("Contact")
        return existing

    # Incluir user_id y email (del token) para que el INSERT funcione
    # si el contacto aún no existe en crm.contacts
    upsert_data: dict = {**update_data, "user_id": user_id}
    email = getattr(user, "email", None)
    if email:
        upsert_data.setdefault("email", email)

    result = (
        await db.schema("crm")
        .table("contacts")
        .upsert(upsert_data, on_conflict="user_id")
        .execute()
    )
    if not result.data:
        raise NotFoundError("Contact")

    saved_contact = result.data[0]

    # Auto-completar steps de tipo profile_field cubiertos por los campos guardados
    try:
        await _try_complete_profile_field_steps(db, user_id, saved_contact, set(update_data.keys()))
    except Exception:
        logger.exception("profile_field: unexpected error for user=%s", user_id)

    # Intentar otorgar puntos de gamificación por completitud de perfil (fire & forget)
    try:
        await _try_award_profile_completion_points(db, user_id, saved_contact)
    except Exception:
        logger.exception("profile_completion: unexpected error for user=%s", user_id)

    return saved_contact


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    ctx: CrmContext = Depends(CrmGlobalWriteAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    # Platform admins pueden actualizar cualquier contacto sin org_id
    if ctx.organization_id:
        belongs = await crud_contacts.contact_belongs_to_org(
            db, str(contact_id), ctx.organization_id
        )
        if not belongs:
            raise ForbiddenError("El contacto no pertenece a tu organización")
    elif not ctx.is_platform_admin:
        raise ForbiddenError("organization_id es requerido")

    updated = await crud_contacts.update_contact(
        db, str(contact_id), data, changed_by=ctx.user_id,
    )
    if not updated:
        raise NotFoundError("Contact")
    return updated


# ---------------------------------------------------------------------------
# Sub-resources: Notes
# ---------------------------------------------------------------------------
@router.get(
    "/{contact_id}/notes",
    response_model=list[NoteResponse],
    summary="Listar notas de un contacto",
)
async def list_contact_notes(
    contact_id: UUID,
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_notes.get_notes_for_contact(
        db, str(contact_id), ctx.organization_id
    )


@router.post(
    "/{contact_id}/notes",
    response_model=NoteResponse,
    status_code=201,
    summary="Crear nota para un contacto",
)
async def create_contact_note(
    contact_id: UUID,
    note_in: NoteCreate,
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_notes.create_note(
        db,
        contact_user_id=str(contact_id),
        organization_id=ctx.organization_id,
        author_id=ctx.user_id,
        note_in=note_in,
    )


# ---------------------------------------------------------------------------
# Sub-resources: Tasks
# ---------------------------------------------------------------------------
@router.get(
    "/{contact_id}/tasks",
    response_model=list[TaskResponse],
    summary="Listar tareas de un contacto",
)
async def list_contact_tasks(
    contact_id: UUID,
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_tasks.get_tasks_for_contact(
        db, str(contact_id), ctx.organization_id
    )


@router.post(
    "/{contact_id}/tasks",
    response_model=TaskResponse,
    status_code=201,
    summary="Crear tarea para un contacto",
)
async def create_contact_task(
    contact_id: UUID,
    task_in: TaskCreate,
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_tasks.create_task(
        db,
        contact_user_id=str(contact_id),
        organization_id=ctx.organization_id,
        creator_id=ctx.user_id,
        task_in=task_in,
    )


# ---------------------------------------------------------------------------
# Timeline (notes + tasks merged, sorted by date)
# ---------------------------------------------------------------------------
@router.get(
    "/{contact_id}/timeline",
    summary="Timeline de un contacto (notas + tareas)",
)
async def get_contact_timeline(
    contact_id: UUID,
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    notes = await crud_notes.get_notes_for_contact(
        db, str(contact_id), ctx.organization_id
    )
    tasks = await crud_tasks.get_tasks_for_contact(
        db, str(contact_id), ctx.organization_id
    )

    timeline = []
    for n in notes:
        timeline.append({**n, "type": "note"})
    for t in tasks:
        timeline.append({**t, "type": "task"})

    timeline.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return timeline


# ---------------------------------------------------------------------------
# Change history (audit trail)
# ---------------------------------------------------------------------------
@router.get(
    "/{contact_id}/changes",
    summary="Historial de cambios de un contacto",
)
async def get_contact_changes(
    contact_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    ctx: CrmContext = Depends(CrmGlobalReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    query = (
        db.schema("crm")
        .table("contact_changes")
        .select("*")
        .eq("contact_user_id", str(contact_id))
        .order("created_at", desc=True)
        .limit(limit)
    )
    result = await query.execute()
    return result.data or []


# ---------------------------------------------------------------------------
# Event participation (cross-schema: journeys.enrollments + public.org_events)
# ---------------------------------------------------------------------------
@router.get(
    "/{user_id}/events",
    response_model=list[ContactEventParticipation],
    summary="Eventos en los que participó un contacto",
)
async def get_contact_events(
    user_id: UUID,
    ctx: CrmContext = Depends(CrmGlobalReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Retorna los eventos vinculados al contacto a través de sus enrollments con event_id."""
    result = await db.rpc(
        "get_contact_events",
        {"p_user_id": str(user_id)},
    ).execute()
    return result.data or []


# ---------------------------------------------------------------------------
# Assign event to contact (admin-side join_event)
# ---------------------------------------------------------------------------
@router.post(
    "/{user_id}/assign-event",
    response_model=AssignEventResponse,
    status_code=201,
    summary="Asignar un evento a un contacto (admin)",
)
async def assign_event_to_contact(
    user_id: UUID,
    body: AssignEventRequest,
    ctx: CrmContext = Depends(CrmGlobalWriteAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Admin-side event assignment: org membership + attendance + journey enrollment."""
    from services.auth_service.logic.event_manager import EventManager

    uid = str(user_id)
    now = datetime.now(timezone.utc).isoformat()

    # 1. Fetch event
    event_resp = (
        await db.schema("crm").table("org_events")
        .select("*")
        .eq("id", body.event_id)
        .single()
        .execute()
    )
    if not event_resp.data:
        raise NotFoundError("Evento")
    event = event_resp.data
    org_id = event["organization_id"]

    # 2. Get journey ids linked to this event
    journey_ids = await EventManager.get_event_journey_ids(body.event_id)
    logger.info("assign_event: user=%s event=%s org=%s journeys=%s", uid, body.event_id, org_id, journey_ids)

    org_joined = False
    attendance_registered = False
    journeys_enrolled: list[str] = []

    # 3. Upsert organization_members (role=participante)
    try:
        await db.schema("public").table("organization_members").upsert(
            {
                "organization_id": org_id,
                "user_id": uid,
                "role": "participante",
                "status": "active",
                "joined_at": now,
            },
            on_conflict="organization_id,user_id",
        ).execute()
        org_joined = True
    except Exception:
        logger.warning("assign_event: failed to upsert org membership user=%s org=%s", uid, org_id)

    # 4. Upsert event_attendances
    try:
        await db.schema("crm").table("event_attendances").upsert(
            {
                "event_id": body.event_id,
                "user_id": uid,
                "status": "registered",
                "modality": body.modality,
                "registered_at": now,
            },
            on_conflict="event_id,user_id",
        ).execute()
        attendance_registered = True
    except Exception:
        logger.warning("assign_event: failed to upsert attendance user=%s event=%s", uid, body.event_id)

    # 5. Enroll in ALL linked journeys (not just the first, unlike self-service)
    for jid in journey_ids:
        try:
            existing = (
                await db.schema("journeys").table("enrollments")
                .select("id")
                .eq("user_id", uid)
                .eq("journey_id", jid)
                .eq("status", "active")
                .execute()
            )
            if not existing.data:
                await db.schema("journeys").table("enrollments").insert(
                    {
                        "user_id": uid,
                        "journey_id": jid,
                        "event_id": body.event_id,
                        "status": "active",
                        "current_step_index": 0,
                        "started_at": now,
                    }
                ).execute()
                logger.info("assign_event: enrolled user=%s journey=%s", uid, jid)
            else:
                logger.info("assign_event: user=%s already enrolled in journey=%s", uid, jid)
            journeys_enrolled.append(jid)
        except Exception:
            logger.exception("assign_event: failed to enroll user=%s journey=%s", uid, jid)

    return AssignEventResponse(
        event_id=body.event_id,
        organization_id=org_id,
        org_joined=org_joined,
        attendance_registered=attendance_registered,
        journeys_enrolled=journeys_enrolled,
    )


# ---------------------------------------------------------------------------
# Remove attendance from contact
# ---------------------------------------------------------------------------
@router.delete(
    "/{user_id}/events/{attendance_id}",
    status_code=204,
    summary="Eliminar asistencia de un contacto a un evento",
)
async def remove_contact_attendance(
    user_id: UUID,
    attendance_id: UUID,
    ctx: CrmContext = Depends(CrmGlobalWriteAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Delete an event_attendances row. Does NOT remove journey enrollments."""
    result = (
        await db.schema("crm").table("event_attendances")
        .delete()
        .eq("id", str(attendance_id))
        .eq("user_id", str(user_id))
        .execute()
    )
    if not result.data:
        raise NotFoundError("Attendance")
    return None