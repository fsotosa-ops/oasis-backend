from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import AsyncClient

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.gamification_service.crud import levels as crud
from services.gamification_service.schemas.levels import LevelCreate, LevelRead, LevelUpdate

router = APIRouter()

require_admin = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/levels",
    response_model=list[LevelRead],
    summary="Listar niveles de la org",
)
async def list_levels(
    org_id: str,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.list_levels(db, UUID(org_id))


@router.post(
    "/{org_id}/admin/levels",
    response_model=LevelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nivel",
)
async def create_level(
    org_id: str,
    payload: LevelCreate,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.create_level(db, UUID(org_id), payload)


@router.patch(
    "/{org_id}/admin/levels/{level_id}",
    response_model=LevelRead,
    summary="Actualizar nivel",
)
async def update_level(
    org_id: str,
    level_id: UUID,
    payload: LevelUpdate,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    existing = await crud.get_level(db, level_id)
    if not existing:
        raise NotFoundError("Level")
    return await crud.update_level(db, level_id, payload)


@router.delete(
    "/{org_id}/admin/levels/{level_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar nivel",
)
async def delete_level(
    org_id: str,
    level_id: UUID,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud.delete_level(db, level_id)
    if not deleted:
        raise NotFoundError("Level")
