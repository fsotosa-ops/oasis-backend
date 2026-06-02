import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import AsyncClient

from common.auth.security import CurrentUser, UserMemberships
from common.database.client import get_admin_client

logger = logging.getLogger(__name__)

router = APIRouter()


class OnboardingCheckResponse(BaseModel):
    should_show: bool
    journey_id: str | None = None


@router.get(
    "/me/onboarding-check",
    response_model=OnboardingCheckResponse,
    summary="Verificar si el usuario debe completar el onboarding journey",
)
async def onboarding_check(
    current_user: CurrentUser,
    memberships: UserMemberships,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    org_id: str | None = Query(None, description="Target org; defaults to first active membership"),
):
    """
    Returns the next onboarding journey the participant should complete, or
    should_show: false when none is pending.

    Selection logic (delegated to journeys.get_next_onboarding_journey):
    - Only active journeys flagged metadata.is_onboarding = true are considered
    - Journeys already completed by this user (per-enrollment) are excluded
    - Ordered by onboarding_priority ASC NULLS LAST, then created_at ASC
    - Journeys with onboarding_trigger_journey_id are only shown after that
      prerequisite journey is completed (enables contextual mid-flow onboarding)

    Admin/SuperAdmin always get should_show: false (frontend guard handles roles).
    """
    user_id = str(current_user.id)

    active = [m for m in memberships if m.get("status") == "active"]
    if not active:
        return OnboardingCheckResponse(should_show=False)

    # Resolve org: use provided org_id if the user is a member, else first active
    if org_id:
        matching = [m for m in active if m["organization_id"] == org_id]
        org_id = matching[0]["organization_id"] if matching else active[0]["organization_id"]
    else:
        org_id = active[0]["organization_id"]

    try:
        result = await db.rpc(
            "get_next_onboarding_journey",
            {"p_user_id": user_id, "p_org_id": org_id},
        ).execute()

        journey_id = result.data  # UUID string or None

        if not journey_id:
            return OnboardingCheckResponse(should_show=False)

        return OnboardingCheckResponse(should_show=True, journey_id=str(journey_id))

    except Exception:
        logger.exception(
            "onboarding-check failed for user=%s org=%s", user_id, org_id,
        )
        return OnboardingCheckResponse(should_show=False)
