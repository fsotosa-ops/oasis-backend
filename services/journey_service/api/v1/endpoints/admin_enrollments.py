from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import AdminUser
from common.database.client import get_admin_client
from services.journey_service.crud import enrollments as crud
from services.journey_service.schemas.enrollments import EnrollmentResponse
from supabase import AsyncClient

router = APIRouter(prefix="/admin/enrollments")


@router.get(
    "/user/{user_id}",
    response_model=list[EnrollmentResponse],
    summary="[Admin] Enrollments de un usuario",
)
async def get_user_enrollments_admin(
    user_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """List all enrollments for a given user. Platform admin only."""
    enrollments = await crud.get_user_enrollments(db, user_id)

    return [
        EnrollmentResponse(
            id=e["id"],
            user_id=e["user_id"],
            journey_id=e["journey_id"],
            organization_id=e.get("organization_id"),
            status=e["status"],
            current_step_index=e["current_step_index"],
            progress_percentage=e.get("progress_percentage", 0.0),
            started_at=e["started_at"],
            completed_at=e.get("completed_at"),
        )
        for e in enrollments
    ]
