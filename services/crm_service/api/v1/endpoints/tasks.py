from uuid import UUID

from fastapi import APIRouter, Depends, Query

from common.auth.security import get_current_user, get_user_memberships
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.crm_service.crud import tasks as crud_tasks
from services.crm_service.dependencies import (
    CrmContext,
    CrmReadAccess,
    _check_platform_admin,
    _find_membership,
)
from services.crm_service.schemas.tasks import TaskResponse, TaskUpdate
from supabase import AsyncClient

router = APIRouter()


@router.get("/", response_model=list[TaskResponse], summary="Lista global de tareas")
async def list_tasks(
    assigned_to: UUID | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    tasks, _ = await crud_tasks.get_tasks_global(
        db=db,
        organization_id=ctx.organization_id,
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
    memberships: list[dict] = Depends(get_user_memberships),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    # Fetch the task first
    task = await crud_tasks.get_task_by_id(db, str(task_id))
    if not task:
        raise NotFoundError("Task")

    org_id = task["organization_id"]
    is_pa = _check_platform_admin(user, memberships)

    # Platform admins can update any task
    if is_pa:
        updated = await crud_tasks.update_task(db, str(task_id), task_in)
        if not updated:
            raise NotFoundError("Task")
        return updated

    # Non-admin: must be member of the task's org
    membership = _find_membership(memberships, org_id)
    if not membership:
        raise ForbiddenError("No eres miembro de esta organización")

    if membership["role"] not in ("facilitador", "admin", "owner"):
        raise ForbiddenError("Rol insuficiente para editar tareas")

    updated = await crud_tasks.update_task_scoped(
        db, str(task_id), org_id, task_in
    )
    if not updated:
        raise NotFoundError("Task")
    return updated


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    user=Depends(get_current_user),  # noqa: B008
    memberships: list[dict] = Depends(get_user_memberships),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    # Fetch the task first
    task = await crud_tasks.get_task_by_id(db, str(task_id))
    if not task:
        raise NotFoundError("Task")

    org_id = task["organization_id"]
    is_pa = _check_platform_admin(user, memberships)

    # Platform admins can delete any task
    if is_pa:
        deleted = await crud_tasks.delete_task(db, str(task_id))
        if not deleted:
            raise NotFoundError("Task")
        return

    # Non-admin: must be member of the task's org
    membership = _find_membership(memberships, org_id)
    if not membership:
        raise ForbiddenError("No eres miembro de esta organización")

    if membership["role"] not in ("facilitador", "admin", "owner"):
        raise ForbiddenError("Rol insuficiente para eliminar tareas")

    deleted = await crud_tasks.delete_task_scoped(db, str(task_id), org_id)
    if not deleted:
        raise NotFoundError("Task")
