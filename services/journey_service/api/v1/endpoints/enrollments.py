import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status

from common.auth.security import CurrentUser, get_current_token
from common.database.client import get_admin_client
from common.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from services.journey_service.crud import enrollments as crud
from services.journey_service.schemas.enrollments import (
    EnrollmentCreate,
    EnrollmentDetailResponse,
    EnrollmentResponse,
    StepCompleteRequest,
    StepCompleteResponse,
    StepProgressRead,
)
from supabase import AsyncClient

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inscribirse en un journey",
)
async def enroll_user(
    payload: EnrollmentCreate,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    existing = await crud.get_active_enrollment(db, user_id, payload.journey_id)
    if existing:
        raise ConflictError("Ya tienes una inscripcion activa en este Journey.")

    new_enrollment = await crud.create_enrollment(
        db, user_id, payload.journey_id
    )

    return EnrollmentResponse(
        id=new_enrollment["id"],
        user_id=new_enrollment["user_id"],
        journey_id=new_enrollment["journey_id"],
        status=new_enrollment["status"],
        current_step_index=new_enrollment["current_step_index"],
        progress_percentage=0.0,
        started_at=new_enrollment["started_at"],
    )


@router.get(
    "/me",
    response_model=list[EnrollmentResponse],
    summary="Mis inscripciones",
)
async def get_my_enrollments(
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    status_filter: str | None = None,
):
    user_id = UUID(str(current_user.id))

    enrollments = await crud.get_user_enrollments(db, user_id, status_filter)

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


@router.get(
    "/{enrollment_id}",
    response_model=EnrollmentDetailResponse,
    summary="Detalle de inscripcion con progreso",
)
async def get_enrollment_detail(
    enrollment_id: UUID,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    enrollment = await crud.get_enrollment_with_progress(db, enrollment_id)

    if not enrollment:
        raise NotFoundError("Enrollment")

    if enrollment["user_id"] != str(user_id):
        raise ForbiddenError("No tienes acceso a esta inscripcion.")

    return enrollment


@router.get(
    "/{enrollment_id}/progress",
    response_model=list[StepProgressRead],
    summary="Progreso step-by-step",
)
async def get_enrollment_progress(
    enrollment_id: UUID,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    enrollment = await crud.get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        raise NotFoundError("Enrollment")

    if enrollment["user_id"] != str(user_id):
        raise ForbiddenError("No tienes acceso a esta inscripcion.")

    progress = await crud.get_enrollment_step_progress(db, enrollment_id)
    return progress


@router.post(
    "/{enrollment_id}/steps/{step_id}/complete",
    response_model=StepCompleteResponse,
    summary="Completar step individual",
)
async def complete_step(
    enrollment_id: UUID,
    step_id: UUID,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    body: StepCompleteRequest | None = None,
):
    user_id = UUID(str(current_user.id))

    enrollment = await crud.get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        raise NotFoundError("Enrollment")

    if enrollment["user_id"] != str(user_id):
        raise ForbiddenError("No tienes acceso a esta inscripcion.")

    if enrollment["status"] != "active":
        raise ConflictError("Solo se pueden completar steps en enrollments activos.")

    belongs = await crud.verify_step_in_enrollment_journey(db, enrollment_id, step_id)
    if not belongs:
        raise ValidationError("El step no pertenece al journey de esta inscripcion.")

    already = await crud.is_step_already_completed(db, enrollment_id, step_id)
    if already:
        raise ConflictError("Este step ya fue completado.")

    metadata = body.metadata if body else None
    external_reference = body.external_reference if body else None
    service_data = body.service_data if body else None

    # If the step is a profile_question, save the answer to CRM contact
    step = await crud.get_step_by_id(db, step_id)
    if step and step.get("type") == "profile_question":
        config = step.get("config") or {}
        field_name = config.get("field_name")
        answer = (metadata or {}).get("answer")
        if field_name and answer is not None:
            try:
                user_id_str = str(current_user.id)
                upsert_data = {"user_id": user_id_str, field_name: answer}
                email = getattr(current_user, "email", None)
                if email:
                    upsert_data["email"] = email
                await db.schema("crm").table("contacts").upsert(
                    upsert_data, on_conflict="user_id"
                ).execute()
                logger.info(
                    "profile_question: saved %s=%s for user=%s",
                    field_name, answer, user_id_str,
                )
            except Exception:
                logger.exception("profile_question: failed to save CRM field for user=%s", str(current_user.id))

    completion = await crud.complete_step(
        db, enrollment_id, step_id,
        metadata=metadata,
        external_reference=external_reference,
        service_data=service_data,
    )

    updated_enrollment = await crud.get_enrollment_by_id(db, enrollment_id)
    progress = updated_enrollment.get("progress_percentage", 0.0) if updated_enrollment else 0.0

    return StepCompleteResponse(
        step_id=completion["step_id"],
        completed_at=completion["completed_at"],
        enrollment_progress=progress,
        points_earned=completion.get("points_earned", 0),
    )


@router.post(
    "/{enrollment_id}/complete",
    response_model=EnrollmentResponse,
    summary="Completar journey entero",
)
async def complete_enrollment(
    enrollment_id: UUID,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    enrollment = await crud.get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        raise NotFoundError("Enrollment")

    if enrollment["user_id"] != str(user_id):
        raise ForbiddenError("No tienes acceso a esta inscripcion.")

    if enrollment["status"] == "completed":
        raise ConflictError("Este journey ya esta completado.")

    can_complete, message = await crud.can_complete_enrollment(db, enrollment_id)
    if not can_complete:
        raise ConflictError(message)

    updated = await crud.update_enrollment_status(db, enrollment_id, "completed")

    return EnrollmentResponse(**updated)


@router.post(
    "/{enrollment_id}/drop",
    response_model=EnrollmentResponse,
    summary="Abandonar journey",
)
async def drop_enrollment(
    enrollment_id: UUID,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    enrollment = await crud.get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        raise NotFoundError("Enrollment")

    if enrollment["user_id"] != str(user_id):
        raise ForbiddenError("No tienes acceso a esta inscripcion.")

    if enrollment["status"] != "active":
        raise ConflictError(
            f"No se puede abandonar un journey con estado '{enrollment['status']}'."
        )

    updated = await crud.update_enrollment_status(db, enrollment_id, "dropped")

    return EnrollmentResponse(**updated)


@router.post(
    "/{enrollment_id}/resume",
    response_model=EnrollmentResponse,
    summary="Retomar journey abandonado",
)
async def resume_enrollment(
    enrollment_id: UUID,
    current_user: CurrentUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    user_id = UUID(str(current_user.id))

    enrollment = await crud.get_enrollment_by_id(db, enrollment_id)
    if not enrollment:
        raise NotFoundError("Enrollment")

    if enrollment["user_id"] != str(user_id):
        raise ForbiddenError("No tienes acceso a esta inscripcion.")

    if enrollment["status"] != "dropped":
        raise ConflictError(
            f"Solo se pueden retomar journeys abandonados. Estado actual: '{enrollment['status']}'."
        )

    updated = await crud.update_enrollment_status(db, enrollment_id, "active")

    return EnrollmentResponse(**updated)
