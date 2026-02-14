from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import AdminUser
from common.database.client import get_admin_client
from services.journey_service.crud import enrollments as crud
from services.journey_service.schemas.enrollments import EnrollmentDetailResponse, EnrollmentResponse
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
            journey_title=e.get("journey_title"),
            status=e["status"],
            current_step_index=e["current_step_index"],
            progress_percentage=e.get("progress_percentage", 0.0),
            started_at=e["started_at"],
            completed_at=e.get("completed_at"),
        )
        for e in enrollments
    ]


@router.get(
    "/user/{user_id}/details",
    response_model=list[EnrollmentDetailResponse],
    summary="[Admin] Enrollments de un usuario con progreso de steps",
)
async def get_user_enrollments_details_admin(
    user_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """List all enrollments for a user with step-by-step progress. Platform admin only."""
    enrollments = await crud.get_user_enrollments(db, user_id)

    details = []
    for e in enrollments:
        detail = await crud.get_enrollment_with_progress(db, UUID(e["id"]))
        if detail:
            details.append(detail)

    return details