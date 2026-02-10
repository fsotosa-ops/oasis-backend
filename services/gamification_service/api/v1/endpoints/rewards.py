from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import AsyncClient

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.gamification_service.crud import rewards as crud
from services.gamification_service.schemas.rewards import RewardCreate, RewardRead, RewardUpdate

router = APIRouter()

require_admin = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/rewards",
    response_model=list[RewardRead],
    summary="Listar catalogo de rewards",
)
async def list_rewards(
    org_id: str,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.list_rewards(db, UUID(org_id))


@router.post(
    "/{org_id}/admin/rewards",
    response_model=RewardRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear reward/badge",
)
async def create_reward(
    org_id: str,
    payload: RewardCreate,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.create_reward(db, UUID(org_id), payload)


@router.patch(
    "/{org_id}/admin/rewards/{reward_id}",
    response_model=RewardRead,
    summary="Actualizar reward",
)
async def update_reward(
    org_id: str,
    reward_id: UUID,
    payload: RewardUpdate,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    existing = await crud.get_reward(db, reward_id)
    if not existing:
        raise NotFoundError("Reward")
    return await crud.update_reward(db, reward_id, payload)


@router.delete(
    "/{org_id}/admin/rewards/{reward_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar reward",
)
async def delete_reward(
    org_id: str,
    reward_id: UUID,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud.delete_reward(db, reward_id)
    if not deleted:
        raise NotFoundError("Reward")
