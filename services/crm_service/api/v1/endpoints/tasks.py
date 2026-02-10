from uuid import UUID

from fastapi import APIRouter, Depends, Query

from common.auth.security import get_current_user
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.crm_service.crud import tasks as crud_tasks
from services.crm_service.schemas.tasks import TaskResponse, TaskUpdate
from supabase import AsyncClient

router = APIRouter()


@router.get("/", response_model=list[TaskResponse], summary="Lista global de tareas")
async def list_tasks(
    organization_id: UUID = Query(...),
    assigned_to: UUID | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    tasks, _ = await crud_tasks.get_tasks_global(
        db=db,
        organization_id=str(organization_id),
        assigned_to=str(assigned_to) if assigned_to else None,
        status=status,
        limit=limit,
        offset=skip,
    )
    return tasks


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task_in: TaskUpdate,
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud_tasks.update_task(db, str(task_id), task_in)
    if not updated:
        raise NotFoundError("Task")
    return updated


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud_tasks.delete_task(db, str(task_id))
    if not deleted:
        raise NotFoundError("Task")
