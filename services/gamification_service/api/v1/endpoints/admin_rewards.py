from uuid import UUID

from fastapi import APIRouter, Depends, status
from supabase import AsyncClient

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.gamification_service.crud import user_rewards as crud
from services.gamification_service.schemas.rewards import UserRewardGrant, UserRewardRead

router = APIRouter()

require_admin = OrgRoleRequired("owner", "admin")


@router.post(
    "/{org_id}/admin/user-rewards",
    response_model=UserRewardRead,
    status_code=status.HTTP_201_CREATED,
    summary="Otorgar reward manualmente a usuario",
)
async def grant_reward(
    org_id: str,
    payload: UserRewardGrant,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    result = await crud.grant_reward(db, payload)
    return result


@router.delete(
    "/{org_id}/admin/user-rewards/{user_reward_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revocar reward de usuario",
)
async def revoke_reward(
    org_id: str,
    user_reward_id: UUID,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud.revoke_reward(db, user_reward_id)
    if not deleted:
        raise NotFoundError("UserReward")


@router.get(
    "/{org_id}/admin/user-rewards/{user_id}",
    response_model=list[UserRewardRead],
    summary="Ver rewards de un usuario especifico",
)
async def get_user_rewards(
    org_id: str,
    user_id: UUID,
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.get_user_rewards_for_admin(db, user_id)
