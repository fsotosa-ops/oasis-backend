from uuid import UUID

from fastapi import APIRouter, Depends, Query
from supabase import AsyncClient

from common.auth.security import CurrentUser
from common.database.client import get_admin_client
from services.gamification_service.crud import levels as levels_crud
from services.gamification_service.crud import points as points_crud
from services.gamification_service.crud import user_rewards as user_rewards_crud
from services.gamification_service.schemas.points import (
    ActivityRead,
    PointsLedgerRead,
    UserPointsSummary,
)
from services.gamification_service.schemas.rewards import UserRewardRead

router = APIRouter()


async def _get_user_level(db: AsyncClient, user_id: UUID, total_points: int) -> tuple[dict | None, dict | None]:
    """Get current and next level for user based on total points.
    Searches across all orgs (global + org-specific levels)."""
    response = (
        await db.schema("journeys").table("levels")
        .select("*")
        .order("min_points")
        .execute()
    )
    all_levels = response.data or []

    current_level = None
    next_level = None

    for level in all_levels:
        if level["min_points"] <= total_points:
            current_level = level
        else:
            next_level = level
            break

    return current_level, next_level


@router.get(
    "/me/summary",
    response_model=UserPointsSummary,
    summary="Resumen completo de gamificacion del usuario",
)
async def get_user_summary(
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    total_points = await points_crud.get_user_total_points(db, user_id)
    current_level, next_level = await _get_user_level(db, user_id, total_points)
    rewards = await user_rewards_crud.get_user_rewards(db, user_id)
    activities = await points_crud.get_user_activities(db, user_id, limit=10)

    points_to_next = None
    if next_level:
        points_to_next = next_level["min_points"] - total_points

    return UserPointsSummary(
        total_points=total_points,
        current_level=current_level,
        next_level=next_level,
        points_to_next_level=points_to_next,
        rewards=rewards,
        recent_activities=activities,
    )


@router.get(
    "/me/points",
    response_model=int,
    summary="Puntos totales del usuario",
)
async def get_user_points(
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))
    return await points_crud.get_user_total_points(db, user_id)


@router.get(
    "/me/rewards",
    response_model=list[UserRewardRead],
    summary="Badges/rewards ganados del usuario",
)
async def get_user_rewards(
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))
    return await user_rewards_crud.get_user_rewards(db, user_id)


@router.get(
    "/me/activities",
    response_model=list[ActivityRead],
    summary="Historial de actividades del usuario",
)
async def get_user_activities(
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    limit: int = Query(default=20, ge=1, le=100),
):
    user_id = UUID(str(current_user.id))
    return await points_crud.get_user_activities(db, user_id, limit=limit)


@router.get(
    "/me/ledger",
    response_model=list[PointsLedgerRead],
    summary="Ledger transaccional de puntos",
)
async def get_user_ledger(
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),
):
    user_id = UUID(str(current_user.id))
    return await points_crud.get_user_points_ledger(db, user_id, limit=limit)
