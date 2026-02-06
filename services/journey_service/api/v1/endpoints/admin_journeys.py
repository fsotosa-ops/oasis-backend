from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from common.auth.security import AdminUser, OrgRoleRequired, get_current_user
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.journey_service.crud import journeys as crud
from services.journey_service.schemas.journeys import (
    JourneyAdminRead,
    JourneyCreate,
    JourneyUpdate,
)
from supabase import AsyncClient

router = APIRouter()

AdminRequired = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/journeys",
    response_model=list[JourneyAdminRead],
    summary="Listar journeys (Admin)",
)
async def list_journeys_admin(
    org_id: str,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    is_active: bool | None = Query(None, description="Filtrar por estado activo"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    journeys, _ = await crud.list_journeys_admin(
        db=db,
        org_id=org_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return journeys


@router.post(
    "/{org_id}/admin/journeys",
    response_model=JourneyAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear journey",
)
async def create_journey(
    org_id: str,
    payload: JourneyCreate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    journey = await crud.create_journey(db, org_id, payload)

    journey["total_steps"] = 0
    journey["total_enrollments"] = 0
    journey["active_enrollments"] = 0
    journey["completed_enrollments"] = 0
    journey["completion_rate"] = 0.0

    return journey


@router.get(
    "/{org_id}/admin/journeys/{journey_id}",
    response_model=JourneyAdminRead,
    summary="Detalle journey (Admin)",
)
async def get_journey_admin(
    org_id: str,
    journey_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    is_platform_admin = user.user_metadata.get("is_platform_admin", False)
    if not is_platform_admin:
        if not await crud.verify_journey_accessible_by_org(db, journey_id, org_id):
            raise ForbiddenError("No tienes acceso a este journey.")

    journey = await crud.get_journey_admin(db, journey_id)

    if not journey:
        raise NotFoundError("Journey")

    return journey


@router.patch(
    "/{org_id}/admin/journeys/{journey_id}",
    response_model=JourneyAdminRead,
    summary="Actualizar journey",
)
async def update_journey(
    org_id: str,
    journey_id: UUID,
    payload: JourneyUpdate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud.update_journey(db, journey_id, payload)

    if not updated:
        raise NotFoundError("Journey")

    journey = await crud.get_journey_admin(db, journey_id)
    return journey


@router.delete(
    "/{org_id}/admin/journeys/{journey_id}",
    summary="Eliminar journey",
)
async def delete_journey(
    org_id: str,
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud.delete_journey(db, journey_id)

    if not deleted:
        raise NotFoundError("Journey")

    return {"deleted_id": str(journey_id)}


@router.post(
    "/{org_id}/admin/journeys/{journey_id}/publish",
    response_model=JourneyAdminRead,
    summary="Publicar journey",
)
async def publish_journey(
    org_id: str,
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    await crud.publish_journey(db, journey_id)
    journey = await crud.get_journey_admin(db, journey_id)
    return journey


@router.post(
    "/{org_id}/admin/journeys/{journey_id}/archive",
    response_model=JourneyAdminRead,
    summary="Archivar journey",
)
async def archive_journey(
    org_id: str,
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    await crud.archive_journey(db, journey_id)
    journey = await crud.get_journey_admin(db, journey_id)
    return journey
