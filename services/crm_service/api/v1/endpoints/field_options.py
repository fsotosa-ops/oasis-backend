from uuid import UUID

from fastapi import APIRouter, Depends, Query

from common.auth.security import AdminUser, CurrentUser
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.crm_service.crud import field_options as crud
from services.crm_service.schemas.contacts import (
    FieldOptionCreate,
    FieldOptionResponse,
    FieldOptionUpdate,
)
from supabase import AsyncClient

router = APIRouter()


@router.get("/", response_model=list[FieldOptionResponse])
async def list_field_options(
    _user: CurrentUser,
    field_name: str | None = Query(None, description="Filter by field name: gender, education_level, occupation"),
    include_inactive: bool = Query(False),
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Lista opciones de campos configurables. Accesible para todos los usuarios autenticados."""
    return await crud.list_field_options(db, field_name, include_inactive)


@router.post("/", response_model=FieldOptionResponse, status_code=201)
async def create_field_option(
    data: FieldOptionCreate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Crea una nueva opción para un campo configurable (solo platform admin)."""
    return await crud.create_field_option(db, data)


@router.patch("/{option_id}", response_model=FieldOptionResponse)
async def update_field_option(
    option_id: UUID,
    data: FieldOptionUpdate,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Actualiza una opción existente (solo platform admin)."""
    updated = await crud.update_field_option(db, str(option_id), data)
    if not updated:
        raise NotFoundError("FieldOption")
    return updated


@router.delete("/{option_id}", status_code=204)
async def delete_field_option(
    option_id: UUID,
    _admin: AdminUser,
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    """Elimina una opción (solo platform admin)."""
    await crud.delete_field_option(db, str(option_id))
    return None