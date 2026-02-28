from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import AsyncClient

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from services.gamification_service.crud import recalculate as crud

router = APIRouter()

require_admin = OrgRoleRequired("owner", "admin")


class RecalculateResponse(BaseModel):
    updated: int
    message: str


@router.post(
    "/{org_id}/admin/recalculate-points",
    response_model=RecalculateResponse,
    summary="Recalcular puntos de step_completions con base_points actuales",
)
async def recalculate_points(
    org_id: str,
    journey_id: str | None = Query(default=None, description="Filtrar por journey"),
    _ctx=Depends(require_admin),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud.recalculate_points(db, UUID(org_id), journey_id=UUID(journey_id) if journey_id else None)
    return RecalculateResponse(
        updated=updated,
        message=f"{updated} registros de puntos recalculados.",
    )
