from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import CurrentUser, get_user_memberships
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.resource_service.crud import resource_consumptions as cons_crud
from services.resource_service.crud import resources as crud
from services.resource_service.crud import unlock_evaluator
from services.resource_service.schemas.resources import (
    ConsumptionCreate,
    ConsumptionRead,
    ResourceParticipantRead,
)
from supabase import AsyncClient

router = APIRouter()


@router.get(
    "/me/resources",
    response_model=list[ResourceParticipantRead],
    summary="Listar mis recursos disponibles",
)
async def list_my_resources(
    user: CurrentUser,
    memberships: list[dict] = Depends(get_user_memberships),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_org_ids = [m["organization_id"] for m in memberships if m.get("status") == "active"]
    resources = await crud.list_resources_for_user(db, user_org_ids)

    resource_ids = [r["id"] for r in resources]
    consumptions = await cons_crud.get_user_consumptions_batch(db, user.id, resource_ids)

    result = []
    for r in resources:
        is_unlocked, lock_reasons = await unlock_evaluator.evaluate_unlock(db, r, user.id)
        consumption = consumptions.get(r["id"])
        is_consumed = bool(consumption and consumption.get("completed_at"))

        result.append(ResourceParticipantRead(
            id=r["id"],
            title=r["title"],
            description=r.get("description"),
            type=r["type"],
            content_url=r.get("content_url") if is_unlocked else None,
            storage_path=r.get("storage_path") if is_unlocked else None,
            thumbnail_url=r.get("thumbnail_url"),
            points_on_completion=r.get("points_on_completion", 0),
            is_unlocked=is_unlocked,
            is_consumed=is_consumed,
            lock_reasons=lock_reasons,
        ))

    return result


@router.get(
    "/me/resources/{resource_id}",
    response_model=ResourceParticipantRead,
    summary="Detalle de un recurso",
)
async def get_my_resource(
    resource_id: UUID,
    user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_for_user(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    is_unlocked, lock_reasons = await unlock_evaluator.evaluate_unlock(db, resource, user.id)
    consumption = await cons_crud.get_user_consumption(db, resource_id, user.id)
    is_consumed = bool(consumption and consumption.get("completed_at"))

    return ResourceParticipantRead(
        id=resource["id"],
        title=resource["title"],
        description=resource.get("description"),
        type=resource["type"],
        content_url=resource.get("content_url") if is_unlocked else None,
        storage_path=resource.get("storage_path") if is_unlocked else None,
        thumbnail_url=resource.get("thumbnail_url"),
        points_on_completion=resource.get("points_on_completion", 0),
        is_unlocked=is_unlocked,
        is_consumed=is_consumed,
        lock_reasons=lock_reasons,
    )


@router.post(
    "/me/resources/{resource_id}/open",
    response_model=ConsumptionRead,
    summary="Registrar apertura de recurso",
)
async def open_resource(
    resource_id: UUID,
    user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_for_user(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    is_unlocked, _ = await unlock_evaluator.evaluate_unlock(db, resource, user.id)
    if not is_unlocked:
        raise ForbiddenError("Este recurso esta bloqueado.")

    consumption = await cons_crud.open_resource(db, resource_id, user.id)
    return consumption


@router.post(
    "/me/resources/{resource_id}/complete",
    response_model=ConsumptionRead,
    summary="Completar recurso y recibir puntos",
)
async def complete_resource(
    resource_id: UUID,
    user: CurrentUser,
    payload: ConsumptionCreate = None,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_for_user(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    is_unlocked, _ = await unlock_evaluator.evaluate_unlock(db, resource, user.id)
    if not is_unlocked:
        raise ForbiddenError("Este recurso esta bloqueado.")

    time_seconds = payload.time_on_page_seconds if payload else 0
    points = resource.get("points_on_completion", 0)

    consumption = await cons_crud.complete_resource(
        db, resource_id, user.id, points, time_seconds
    )
    return consumption
