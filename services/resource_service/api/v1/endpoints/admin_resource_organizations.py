from uuid import UUID

from fastapi import APIRouter, Depends, status

from common.auth.security import AdminUser, CurrentUser
from common.database.client import get_admin_client
from common.exceptions import NotFoundError, ValidationError
from services.resource_service.crud import resource_organizations as ro_crud
from services.resource_service.crud import resources as crud
from services.resource_service.schemas.resources import (
    ResourceOrganizationAssign,
    ResourceOrganizationUnassign,
    ResourceOrganizationsResponse,
)
from supabase import AsyncClient

router = APIRouter()


@router.get(
    "/admin/resources/{resource_id}/organizations",
    response_model=ResourceOrganizationsResponse,
    summary="Listar organizaciones asignadas a un recurso",
)
async def list_resource_organizations(
    resource_id: UUID,
    _user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_admin(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    orgs = await ro_crud.get_assigned_orgs(db, resource_id)
    return ResourceOrganizationsResponse(
        resource_id=resource_id,
        organizations=orgs,
        total=len(orgs),
    )


@router.post(
    "/admin/resources/{resource_id}/organizations",
    response_model=ResourceOrganizationsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar recurso a organizaciones",
)
async def assign_resource_to_organizations(
    resource_id: UUID,
    payload: ResourceOrganizationAssign,
    admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_admin(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    await ro_crud.assign_resource_to_orgs(
        db,
        resource_id,
        payload.organization_ids,
        assigned_by=admin.id,
    )

    orgs = await ro_crud.get_assigned_orgs(db, resource_id)
    return ResourceOrganizationsResponse(
        resource_id=resource_id,
        organizations=orgs,
        total=len(orgs),
    )


@router.delete(
    "/admin/resources/{resource_id}/organizations",
    response_model=ResourceOrganizationsResponse,
    summary="Desasignar recurso de organizaciones",
)
async def unassign_resource_from_organizations(
    resource_id: UUID,
    payload: ResourceOrganizationUnassign,
    _admin: AdminUser,  # cross-org operation: platform admin only
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_admin(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    owner_org_id = resource["organization_id"]
    for org_id in payload.organization_ids:
        if str(org_id) == owner_org_id:
            raise ValidationError(
                "No se puede desasignar la organizacion propietaria del recurso."
            )

    await ro_crud.unassign_resource_from_orgs(db, resource_id, payload.organization_ids)

    orgs = await ro_crud.get_assigned_orgs(db, resource_id)
    return ResourceOrganizationsResponse(
        resource_id=resource_id,
        organizations=orgs,
        total=len(orgs),
    )