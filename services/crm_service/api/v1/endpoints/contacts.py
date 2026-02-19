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
from supabase import AsyncClient

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
    """Permite a cualquier usuario autenticado actualizar su propio contacto CRM."""
    updated = await crud_contacts.update_contact(
        db, str(user.id), data, changed_by=str(user.id),
    )
    if not updated:
        raise NotFoundError("Contact")
    return updated


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