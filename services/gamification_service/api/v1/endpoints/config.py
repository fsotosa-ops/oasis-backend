from fastapi import APIRouter, Depends
from supabase import AsyncClient

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.gamification_service.crud import config as crud
from services.gamification_service.schemas.config import (
    GamificationConfigCreate,
    GamificationConfigRead,
    GamificationConfigUpdate,
)

router = APIRouter()

require_admin = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/config",
    response_model=GamificationConfigRead | None,
    summary="Obtener configuracion de gamificacion de la org",
)
async def get_config(
    org_id: str,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.get_config(db, org_id)


@router.put(
    "/{org_id}/admin/config",
    response_model=GamificationConfigRead,
    summary="Crear o reemplazar configuracion de gamificacion",
)
async def upsert_config(
    org_id: str,
    payload: GamificationConfigCreate,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.upsert_config(db, org_id, payload)


@router.patch(
    "/{org_id}/admin/config",
    response_model=GamificationConfigRead,
    summary="Actualizar parcialmente configuracion de gamificacion",
)
async def update_config(
    org_id: str,
    payload: GamificationConfigUpdate,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    result = await crud.update_config(db, org_id, payload)
    if not result:
        raise NotFoundError("GamificationConfig")
    return result
