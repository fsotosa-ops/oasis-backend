from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.journey_service.crud import journeys as crud
from services.journey_service.schemas.journeys import JourneyRead
from supabase import AsyncClient

router = APIRouter()

MemberRequired = OrgRoleRequired("owner", "admin", "facilitador", "participante")


@router.get(
    "/{org_id}/journeys",
    response_model=list[JourneyRead],
    summary="Listar journeys activos de la org",
)
async def list_journeys(
    org_id: str,
    _ctx=Depends(MemberRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    is_active: bool | None = Query(True, description="Filtrar por activos"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    all_journeys, _ = await crud.get_journeys_for_org(
        db=db,
        org_id=org_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    # Filter by available_from: hide journeys not yet open for enrollment
    now = datetime.now(timezone.utc)
    journeys = []
    for j in all_journeys:
        af = j.get("available_from")
        if af:
            try:
                af_dt = datetime.fromisoformat(af.replace("Z", "+00:00")) if isinstance(af, str) else af
                if now < af_dt:
                    continue
            except (ValueError, AttributeError):
                pass
        journeys.append(j)
    return journeys


@router.get(
    "/{org_id}/journeys/{journey_id}",
    response_model=JourneyRead,
    summary="Detalle de journey con steps",
)
async def get_journey(
    org_id: str,
    journey_id: UUID,
    _ctx=Depends(MemberRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    accessible = await crud.verify_journey_accessible_by_org(db, journey_id, org_id)
    if not accessible:
        raise ForbiddenError("El journey no pertenece a tu organizacion.")

    journey = await crud.get_journey_with_steps(db, journey_id)

    if not journey:
        raise NotFoundError("Journey")

    return journey
