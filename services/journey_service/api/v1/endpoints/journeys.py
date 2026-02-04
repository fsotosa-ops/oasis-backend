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
    journeys, _ = await crud.get_journeys_for_org(
        db=db,
        org_id=org_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
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
    belongs = await crud.verify_journey_belongs_to_org(db, journey_id, org_id)
    if not belongs:
        raise ForbiddenError("El journey no pertenece a tu organizacion.")

    journey = await crud.get_journey_with_steps(db, journey_id)

    if not journey:
        raise NotFoundError("Journey")

    return journey
