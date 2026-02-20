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
from supabase import AsyncClient

# Campos que se consideran para calcular si el perfil está "completo"
_COMPLETION_FIELDS = ("phone", "birth_date", "gender", "education_level", "occupation", "company", "city")
# Número mínimo de campos requeridos para considerar el perfil completo
_COMPLETION_THRESHOLD = 5


async def _try_award_profile_completion_points(db: AsyncClient, user_id: str, contact: dict) -> None:
    """Otorga puntos y recompensas de completitud de perfil.

    Flujo:
    1. Verifica que el perfil supere el umbral de campos rellenos.
    2. Busca la org del usuario.
    3. Busca recompensas del catálogo con unlock_condition.trigger = 'profile_completion'.
       - Para cada recompensa no otorgada: la concede + registra sus puntos en el ledger.
    4. Fallback: si no hay recompensas con trigger, usa profile_completion_points del config.
    """
    # 1. Verificar si el perfil está completo
    filled = sum(1 for f in _COMPLETION_FIELDS if contact.get(f))
    if filled < _COMPLETION_THRESHOLD:
        return

    # 2. Buscar la organización del usuario
    membership = (
        await db.schema("auth").table("organization_members")
        .select("organization_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not membership.data:
        return
    org_id_str = membership.data[0]["organization_id"]
    org_id = UUID(org_id_str)

    # 3. Buscar recompensas del catálogo con condición "profile_completion"
    # Incluye: propiedad de la org, globales (organization_id NULL), y asignadas por pivot
    catalog_resp = (
        await db.schema("journeys").table("rewards_catalog")
        .select("id, points, unlock_condition")
        .or_(f"organization_id.eq.{org_id_str},organization_id.is.null")
        .execute()
    )
    catalog = catalog_resp.data or []
    catalog_ids = {r["id"] for r in catalog}

    # Vía tabla pivot reward_organizations
    pivot_resp = (
        await db.schema("journeys").table("reward_organizations")
        .select("reward_id")
        .eq("organization_id", org_id_str)
        .execute()
    )
    extra_ids = [r["reward_id"] for r in (pivot_resp.data or []) if r["reward_id"] not in catalog_ids]
    if extra_ids:
        extra_resp = (
            await db.schema("journeys").table("rewards_catalog")
            .select("id, points, unlock_condition")
            .in_("id", extra_ids)
            .execute()
        )
        catalog.extend(extra_resp.data or [])

    def _has_profile_completion_condition(uc: dict) -> bool:
        conditions = uc.get("conditions", [])
        return any(c.get("type") == "profile_completion" for c in conditions)

    trigger_rewards = [
        r for r in catalog
        if isinstance(r.get("unlock_condition"), dict)
        and _has_profile_completion_condition(r["unlock_condition"])
    ]

    if trigger_rewards:
        # Recompensas ya otorgadas a este usuario
        granted_resp = (
            await db.schema("journeys").table("user_rewards")
            .select("reward_id")
            .eq("user_id", user_id)
            .execute()
        )
        already_granted = {str(r["reward_id"]) for r in (granted_resp.data or [])}

        for reward in trigger_rewards:
            reward_id = str(reward["id"])
            if reward_id in already_granted:
                continue  # Ya tiene esta recompensa

            # Otorgar la recompensa
            await db.schema("journeys").table("user_rewards").insert({
                "user_id": user_id,
                "reward_id": reward_id,
                "metadata": {"trigger": "profile_completion", "fields_filled": filled},
            }).execute()

            # Añadir puntos al ledger usando el campo points del reward (campo propio)
            reward_points = reward.get("points", 0) or 0
            if reward_points > 0:
                await db.schema("journeys").table("points_ledger").insert({
                    "user_id": user_id,
                    "organization_id": org_id_str,
                    "amount": reward_points,
                    "reason": "profile_completion",
                    "reference_id": reward_id,
                }).execute()

                await db.schema("journeys").table("user_activities").insert({
                    "user_id": user_id,
                    "organization_id": org_id_str,
                    "type": "profile_completed",
                    "points_awarded": reward_points,
                    "metadata": {"reward_id": reward_id, "fields_filled": filled},
                }).execute()

        return  # Recompensas gestionadas — no ejecutar el fallback

    # 4. Fallback: usar profile_completion_points del config de la org
    # Solo si nunca se han otorgado puntos de perfil anteriormente
    existing_ledger = (
        await db.schema("journeys").table("points_ledger")
        .select("id")
        .eq("user_id", user_id)
        .eq("reason", "profile_completion")
        .limit(1)
        .execute()
    )
    if existing_ledger.data:
        return

    config = await gamif_config_crud.get_config(db, org_id)
    if not config:
        return
    points = config.get("profile_completion_points", 0)
    if not points or points <= 0:
        return

    await db.schema("journeys").table("points_ledger").insert({
        "user_id": user_id,
        "organization_id": org_id_str,
        "amount": points,
        "reason": "profile_completion",
        "reference_id": user_id,
    }).execute()

    await db.schema("journeys").table("user_activities").insert({
        "user_id": user_id,
        "organization_id": org_id_str,
        "type": "profile_completed",
        "points_awarded": points,
        "metadata": {"fields_filled": filled},
    }).execute()

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

    # Intentar otorgar puntos de gamificación por completitud de perfil (fire & forget)
    try:
        await _try_award_profile_completion_points(db, user_id, saved_contact)
    except Exception:
        pass  # No bloquear la respuesta si falla la gamificación

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