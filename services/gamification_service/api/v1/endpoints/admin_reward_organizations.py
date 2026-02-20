from uuid import UUID

from fastapi import APIRouter, Depends, status

from common.auth.security import AdminUser
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.gamification_service.crud import reward_organizations as ro_crud
from services.gamification_service.crud import rewards as rewards_crud
from services.gamification_service.schemas.rewards import (
    RewardOrganizationAssign,
    RewardOrganizationUnassign,
    RewardOrganizationsResponse,
)
from supabase import AsyncClient

router = APIRouter()


@router.get(
    "/admin/rewards/{reward_id}/organizations",
    response_model=RewardOrganizationsResponse,
    summary="Listar organizaciones habilitadas para una recompensa",
)
async def list_reward_organizations(
    reward_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    reward = await rewards_crud.get_reward(db, reward_id)
    if not reward:
        raise NotFoundError("Reward")
    orgs = await ro_crud.get_assigned_orgs(db, reward_id)
    return RewardOrganizationsResponse(reward_id=reward_id, organizations=orgs, total=len(orgs))


@router.post(
    "/admin/rewards/{reward_id}/organizations",
    response_model=RewardOrganizationsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar recompensa a organizaciones",
)
async def assign_reward_to_organizations(
    reward_id: UUID,
    payload: RewardOrganizationAssign,
    admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    reward = await rewards_crud.get_reward(db, reward_id)
    if not reward:
        raise NotFoundError("Reward")
    await ro_crud.assign_to_orgs(db, reward_id, payload.organization_ids, assigned_by=admin.id)
    orgs = await ro_crud.get_assigned_orgs(db, reward_id)
    return RewardOrganizationsResponse(reward_id=reward_id, organizations=orgs, total=len(orgs))


@router.delete(
    "/admin/rewards/{reward_id}/organizations",
    response_model=RewardOrganizationsResponse,
    summary="Desasignar recompensa de organizaciones",
)
async def unassign_reward_from_organizations(
    reward_id: UUID,
    payload: RewardOrganizationUnassign,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    reward = await rewards_crud.get_reward(db, reward_id)
    if not reward:
        raise NotFoundError("Reward")
    await ro_crud.unassign_from_orgs(db, reward_id, payload.organization_ids)
    orgs = await ro_crud.get_assigned_orgs(db, reward_id)
    return RewardOrganizationsResponse(reward_id=reward_id, organizations=orgs, total=len(orgs))
