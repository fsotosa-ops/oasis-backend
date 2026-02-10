from uuid import UUID

from fastapi import APIRouter, Depends, Query

from common.auth.security import get_current_user
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.crm_service.crud import contacts as crud_contacts
from services.crm_service.crud import notes as crud_notes
from services.crm_service.crud import tasks as crud_tasks
from services.crm_service.schemas.contacts import ContactResponse, ContactUpdate
from services.crm_service.schemas.notes import NoteCreate, NoteResponse
from services.crm_service.schemas.tasks import TaskCreate, TaskResponse
from supabase import AsyncClient

router = APIRouter()


@router.get("/", response_model=list[ContactResponse])
async def list_contacts(
    organization_id: UUID | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    contacts, _ = await crud_contacts.get_contacts(
        db=db,
        organization_id=str(organization_id) if organization_id else None,
        search=search,
        limit=limit,
        offset=skip,
    )
    return contacts


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    contact = await crud_contacts.get_contact_by_id(db, str(contact_id))
    if not contact:
        raise NotFoundError("Contact")
    return contact


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud_contacts.update_contact(db, str(contact_id), data)
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
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_notes.get_notes_for_contact(
        db, str(contact_id), str(organization_id)
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
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_notes.create_note(
        db,
        contact_user_id=str(contact_id),
        organization_id=str(organization_id),
        author_id=str(user.id),
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
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_tasks.get_tasks_for_contact(
        db, str(contact_id), str(organization_id)
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
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud_tasks.create_task(
        db,
        contact_user_id=str(contact_id),
        organization_id=str(organization_id),
        creator_id=str(user.id),
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
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    notes = await crud_notes.get_notes_for_contact(
        db, str(contact_id), str(organization_id)
    )
    tasks = await crud_tasks.get_tasks_for_contact(
        db, str(contact_id), str(organization_id)
    )

    timeline = []
    for n in notes:
        timeline.append({**n, "type": "note"})
    for t in tasks:
        timeline.append({**t, "type": "task"})

    timeline.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return timeline
