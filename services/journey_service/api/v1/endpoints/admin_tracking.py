import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from services.journey_service.crud import journeys as crud
from services.journey_service.schemas.journeys import (
    JourneyEnrolleeRead,
    OrgTrackingResponse,
)
from supabase import AsyncClient

logger = logging.getLogger(__name__)

router = APIRouter()

AdminRequired = OrgRoleRequired("owner", "admin")


@router.get(
    "/{org_id}/admin/tracking",
    response_model=OrgTrackingResponse,
    summary="Tracking jerárquico Org → Evento → Journeys",
)
async def get_org_tracking(
    org_id: str,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.list_org_tracking(db, org_id)


@router.get(
    "/{org_id}/admin/tracking/journeys/{journey_id}/enrollees",
    response_model=list[JourneyEnrolleeRead],
    summary="Inscritos a un journey (filtrable por evento y estado)",
)
async def list_journey_enrollees_endpoint(
    org_id: str,
    journey_id: str,
    event_id: str | None = Query(None),
    status: Literal["not_started", "active", "completed"] | None = Query(None),
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    return await crud.list_journey_enrollees(
        db,
        org_id=org_id,
        journey_id=journey_id,
        event_id=event_id,
        status=status,
    )
