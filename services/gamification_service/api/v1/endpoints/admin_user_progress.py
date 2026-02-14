from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import AdminUser
from common.database.client import get_admin_client
from services.gamification_service.crud import levels as levels_crud
from services.gamification_service.crud import points as points_crud
from services.gamification_service.crud import user_rewards as user_rewards_crud
from services.gamification_service.schemas.points import UserPointsSummary
from supabase import AsyncClient

router = APIRouter(prefix="/admin/progress")


async def _get_user_level(
    db: AsyncClient, total_points: int
) -> tuple[dict | None, dict | None]:
    """Get current and next level based on total points."""
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
    "/user/{user_id}/summary",
    response_model=UserPointsSummary,
    summary="[Admin] Resumen de gamificacion de un usuario",
)
async def get_user_summary_admin(
    user_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Get gamification summary for a given user. Platform admin only."""
    total_points = await points_crud.get_user_total_points(db, user_id)
    current_level, next_level = await _get_user_level(db, total_points)
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
