from uuid import UUID

from fastapi import APIRouter, Depends, status

from common.auth.security import AdminUser
from common.database.client import get_admin_client
from common.exceptions import NotFoundError, ValidationError
from services.journey_service.crud import journey_organizations as jo_crud
from services.journey_service.crud import journeys as crud
from services.journey_service.schemas.journeys import (
    JourneyOrganizationAssign,
    JourneyOrganizationsResponse,
    JourneyOrganizationUnassign,
)
from supabase import AsyncClient

router = APIRouter()


@router.get(
    "/admin/journeys/{journey_id}/organizations",
    response_model=JourneyOrganizationsResponse,
    summary="Listar organizaciones asignadas a un journey",
)
async def list_journey_organizations(
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    journey = await crud.get_journey_by_id(db, journey_id)
    if not journey:
        raise NotFoundError("Journey")

    orgs = await jo_crud.get_assigned_orgs(db, journey_id)
    return JourneyOrganizationsResponse(
        journey_id=journey_id,
        organizations=orgs,
        total=len(orgs),
    )


@router.post(
    "/admin/journeys/{journey_id}/organizations",
    response_model=JourneyOrganizationsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar journey a organizaciones",
)
async def assign_journey_to_organizations(
    journey_id: UUID,
    payload: JourneyOrganizationAssign,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    journey = await crud.get_journey_by_id(db, journey_id)
    if not journey:
        raise NotFoundError("Journey")

    await jo_crud.assign_journey_to_orgs(
        db,
        journey_id,
        payload.organization_ids,
        assigned_by=_admin.id,
    )

    orgs = await jo_crud.get_assigned_orgs(db, journey_id)
    return JourneyOrganizationsResponse(
        journey_id=journey_id,
        organizations=orgs,
        total=len(orgs),
    )


@router.delete(
    "/admin/journeys/{journey_id}/organizations",
    response_model=JourneyOrganizationsResponse,
    summary="Desasignar journey de organizaciones",
)
async def unassign_journey_from_organizations(
    journey_id: UUID,
    payload: JourneyOrganizationUnassign,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    journey = await crud.get_journey_by_id(db, journey_id)
    if not journey:
        raise NotFoundError("Journey")

    # Prevent unassigning the owner organization
    owner_org_id = journey["organization_id"]
    for org_id in payload.organization_ids:
        if str(org_id) == owner_org_id:
            raise ValidationError(
                "No se puede desasignar la organizacion propietaria del journey."
            )

    await jo_crud.unassign_journey_from_orgs(db, journey_id, payload.organization_ids)

    orgs = await jo_crud.get_assigned_orgs(db, journey_id)
    return JourneyOrganizationsResponse(
        journey_id=journey_id,
        organizations=orgs,
        total=len(orgs),
    )
