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
    Returns whether the participant should see the onboarding journey gate.
    - No gamification_config.profile_completion_journey_id configured → should_show: false
    - User has a completed enrollment for that journey → should_show: false
    - No enrollment or enrollment.status = 'active' → should_show: true
    Only meaningful for Participant role; Admin/SuperAdmin always get should_show: false
    via the frontend guard.
    """
    user_id = str(current_user.id)

    active = [m for m in memberships if m.get("status") == "active"]
    if not active:
        return OnboardingCheckResponse(should_show=False)

    # Use provided org_id if valid (user must be a member), else first active
    if org_id:
        matching = [m for m in active if m["organization_id"] == org_id]
        if matching:
            org_id = matching[0]["organization_id"]
        else:
            org_id = active[0]["organization_id"]
    else:
        org_id = active[0]["organization_id"]

    try:
        # Fetch gamification config to get profile_completion_journey_id
        config_resp = (
            await db.schema("journeys")
            .table("gamification_config")
            .select("profile_completion_journey_id")
            .eq("organization_id", org_id)
            .maybe_single()
            .execute()
        )
        config = config_resp.data
        if not config or not config.get("profile_completion_journey_id"):
            return OnboardingCheckResponse(should_show=False)

        journey_id = str(config["profile_completion_journey_id"])

        # Check if user has a completed enrollment for this journey
        enrollment_resp = (
            await db.schema("journeys")
            .table("enrollments")
            .select("status")
            .eq("user_id", user_id)
            .eq("journey_id", journey_id)
            .maybe_single()
            .execute()
        )
        enrollment = enrollment_resp.data

        if enrollment and enrollment.get("status") == "completed":
            return OnboardingCheckResponse(should_show=False)

        # No enrollment or active enrollment → show onboarding
        return OnboardingCheckResponse(should_show=True, journey_id=journey_id)
    except Exception:
        logger.exception(
            "onboarding-check failed for user=%s org=%s", user_id, org_id,
        )
        return OnboardingCheckResponse(should_show=False)
