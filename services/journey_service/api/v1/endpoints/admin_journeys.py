import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from common.auth.security import AdminUser, OrgRoleRequired, get_current_user
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.gamification_service.crud import config as gamif_config_crud
from services.gamification_service.schemas.config import (
    GamificationConfigCreate,
    GamificationConfigUpdate,
)
from services.journey_service.api.v1.endpoints.admin_templates import _ONBOARDING_STEPS
from services.journey_service.crud import journeys as crud
from services.journey_service.crud import steps as steps_crud
from services.journey_service.schemas.journeys import (
    GamificationRules,
    JourneyAdminRead,
    JourneyCreate,
    JourneyUpdate,
    StepCreate,
)
from supabase import AsyncClient

logger = logging.getLogger(__name__)

router = APIRouter()

AdminRequired = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/journeys",
    response_model=list[JourneyAdminRead],
    summary="Listar journeys (Admin)",
)
async def list_journeys_admin(
    org_id: str,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    is_active: bool | None = Query(None, description="Filtrar por estado activo"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    journeys, _ = await crud.list_journeys_admin(
        db=db,
        org_id=org_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return journeys


@router.post(
    "/{org_id}/admin/journeys",
    response_model=JourneyAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear journey",
)
async def create_journey(
    org_id: str,
    payload: JourneyCreate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    journey = await crud.create_journey(db, org_id, payload)

    journey["total_steps"] = 0
    journey["total_enrollments"] = 0
    journey["active_enrollments"] = 0
    journey["completed_enrollments"] = 0
    journey["completion_rate"] = 0.0

    return journey


@router.get(
    "/{org_id}/admin/journeys/{journey_id}",
    response_model=JourneyAdminRead,
    summary="Detalle journey (Admin)",
)
async def get_journey_admin(
    org_id: str,
    journey_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    is_platform_admin = user.user_metadata.get("is_platform_admin", False)
    if not is_platform_admin:
        if not await crud.verify_journey_accessible_by_org(db, journey_id, org_id):
            raise ForbiddenError("No tienes acceso a este journey.")

    journey = await crud.get_journey_admin(db, journey_id)

    if not journey:
        raise NotFoundError("Journey")

    return journey


@router.patch(
    "/{org_id}/admin/journeys/{journey_id}",
    response_model=JourneyAdminRead,
    summary="Actualizar journey",
)
async def update_journey(
    org_id: str,
    journey_id: UUID,
    payload: JourneyUpdate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud.update_journey(db, journey_id, payload)

    if not updated:
        raise NotFoundError("Journey")

    # Handle is_onboarding flag atomically
    if payload.is_onboarding is True:
        # Set metadata.is_onboarding so the member-facing page routes to JourneyWizard
        current_metadata = updated.get("metadata") or {}
        current_metadata["is_onboarding"] = True
        await db.schema("journeys").table("journeys").update(
            {"metadata": current_metadata}
        ).eq("id", str(journey_id)).execute()

        # Add template steps if none of type profile_field exist
        existing_steps = await crud.get_steps_by_journey(db, journey_id)
        has_profile_steps = any(
            s.get("type") == "profile_field" for s in existing_steps
        )
        if not has_profile_steps:
            for i, step_def in enumerate(_ONBOARDING_STEPS):
                await steps_crud.create_step(
                    db,
                    journey_id,
                    StepCreate(
                        title=step_def["title"],
                        type="profile_field",
                        order_index=None,
                        config={
                            "field_names": step_def["field_names"],
                            "description": step_def["description"],
                            "icon": step_def["icon"],
                        },
                        gamification_rules=GamificationRules(
                            base_points=step_def["points"]
                        ),
                    ),
                )

        # Upsert gamification_config with profile_completion_journey_id
        org_uuid = UUID(org_id)
        existing_config = await gamif_config_crud.get_config(db, org_uuid) or {}
        config_fields = {
            k: v
            for k, v in existing_config.items()
            if k in GamificationConfigCreate.model_fields
        }
        config_fields["profile_completion_journey_id"] = journey_id
        await gamif_config_crud.upsert_config(
            db, org_uuid, GamificationConfigCreate(**config_fields)
        )

    elif payload.is_onboarding is False:
        # Clear metadata.is_onboarding flag
        current_metadata = updated.get("metadata") or {}
        current_metadata.pop("is_onboarding", None)
        await db.schema("journeys").table("journeys").update(
            {"metadata": current_metadata}
        ).eq("id", str(journey_id)).execute()

        # Clear profile_completion_journey_id
        org_uuid = UUID(org_id)
        await gamif_config_crud.update_config(
            db,
            org_uuid,
            GamificationConfigUpdate(profile_completion_journey_id=None),
        )

    journey = await crud.get_journey_admin(db, journey_id)
    return journey


@router.delete(
    "/{org_id}/admin/journeys/{journey_id}",
    summary="Eliminar journey",
)
async def delete_journey(
    org_id: str,
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud.delete_journey(db, journey_id)

    if not deleted:
        raise NotFoundError("Journey")

    return {"deleted_id": str(journey_id)}


@router.post(
    "/{org_id}/admin/journeys/{journey_id}/publish",
    response_model=JourneyAdminRead,
    summary="Publicar journey",
)
async def publish_journey(
    org_id: str,
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    await crud.publish_journey(db, journey_id)
    journey = await crud.get_journey_admin(db, journey_id)
    return journey


@router.post(
    "/{org_id}/admin/journeys/{journey_id}/archive",
    response_model=JourneyAdminRead,
    summary="Archivar journey",
)
async def archive_journey(
    org_id: str,
    journey_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    await crud.archive_journey(db, journey_id)
    journey = await crud.get_journey_admin(db, journey_id)
    return journey
