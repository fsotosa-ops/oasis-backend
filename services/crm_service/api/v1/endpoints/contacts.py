import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query

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
from services.crm_service.schemas.contacts import ContactResponse, ContactUpdate, PaginatedContactsResponse
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

async def _try_complete_profile_field_steps(db: AsyncClient, user_id: str, contact: dict) -> None:
    """Auto-completa steps de tipo profile_field cuyas field_names ya están todas llenas.

    Flujo:
    1. Busca la org del usuario.
    2. Lee gamification_config para obtener profile_completion_journey_id.
    3. Obtiene todos los steps de ese journey.
    4. Para cada step de tipo profile_field: si todos sus field_names tienen valor en el contacto
       → marca el step como completado (idempotente).
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
        await _try_complete_profile_field_steps(db, user_id, saved_contact)
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