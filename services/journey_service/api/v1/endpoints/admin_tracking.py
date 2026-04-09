import logging

from fastapi import APIRouter, Depends

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from services.journey_service.crud import journeys as crud
from services.journey_service.schemas.journeys import OrgTrackingResponse
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
