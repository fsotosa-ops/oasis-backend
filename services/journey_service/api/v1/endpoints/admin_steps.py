from uuid import UUID

from fastapi import APIRouter, Depends, status

from common.auth.security import AdminUser, OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.journey_service.crud import journeys as journeys_crud
from services.journey_service.crud import steps as crud
from services.journey_service.schemas.journeys import (
    StepAdminRead,
    StepCreate,
    StepReorderRequest,
    StepUpdate,
)
from supabase import AsyncClient

router = APIRouter()

AdminRequired = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/journeys/{journey_id}/steps",
    response_model=list[StepAdminRead],
    summary="Listar steps (Admin)",
)
async def list_steps(
    org_id: str,
    journey_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    if not await journeys_crud.verify_journey_accessible_by_org(db, journey_id, org_id):
        raise ForbiddenError("No tienes acceso a este journey.")

    steps = await crud.list_steps(db, journey_id)
    return steps


@router.post(
    "/{org_id}/admin/journeys/{journey_id}/steps",
    response_model=StepAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear step",
)
async def create_step(
    org_id: str,
    journey_id: UUID,
    payload: StepCreate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    if not await journeys_crud.verify_journey_belongs_to_org(db, journey_id, org_id):
        raise ForbiddenError("No tienes acceso a este journey.")

    step = await crud.create_step(db, journey_id, payload)

    step["total_completions"] = 0
    step["average_points"] = 0.0

    return step


@router.patch(
    "/{org_id}/admin/journeys/{journey_id}/steps/{step_id}",
    response_model=StepAdminRead,
    summary="Actualizar step",
)
async def update_step(
    org_id: str,
    journey_id: UUID,
    step_id: UUID,
    payload: StepUpdate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    if not await journeys_crud.verify_journey_belongs_to_org(db, journey_id, org_id):
        raise ForbiddenError("No tienes acceso a este journey.")

    updated = await crud.update_step(db, step_id, payload)

    if not updated:
        raise NotFoundError("Step")

    return updated


@router.delete(
    "/{org_id}/admin/journeys/{journey_id}/steps/{step_id}",
    summary="Eliminar step",
)
async def delete_step(
    org_id: str,
    journey_id: UUID,
    step_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    if not await journeys_crud.verify_journey_belongs_to_org(db, journey_id, org_id):
        raise ForbiddenError("No tienes acceso a este journey.")

    deleted = await crud.delete_step(db, step_id)

    if not deleted:
        raise NotFoundError("Step")

    return {"deleted_id": str(step_id)}


@router.post(
    "/{org_id}/admin/journeys/{journey_id}/steps/reorder",
    response_model=list[StepAdminRead],
    summary="Reordenar steps",
)
async def reorder_steps(
    org_id: str,
    journey_id: UUID,
    payload: StepReorderRequest,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    if not await journeys_crud.verify_journey_belongs_to_org(db, journey_id, org_id):
        raise ForbiddenError("No tienes acceso a este journey.")

    step_orders = [
        {"step_id": item.step_id, "new_index": item.new_index}
        for item in payload.steps
    ]

    steps = await crud.reorder_steps(db, journey_id, step_orders)
    return steps
