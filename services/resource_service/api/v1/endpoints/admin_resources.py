from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File, status

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.resource_service.crud import resources as crud
from services.resource_service.schemas.resources import (
    ResourceAdminRead,
    ResourceCreate,
    ResourceUpdate,
)
from supabase import AsyncClient

router = APIRouter()

AdminRequired = OrgRoleRequired("owner", "admin", "facilitador")


@router.get(
    "/{org_id}/admin/resources",
    response_model=list[ResourceAdminRead],
    summary="Listar recursos (Admin)",
)
async def list_resources_admin(
    org_id: str,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
    is_published: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    resources, _ = await crud.list_resources_admin(
        db=db,
        org_id=org_id,
        is_published=is_published,
        skip=skip,
        limit=limit,
    )
    return resources


@router.post(
    "/{org_id}/admin/resources",
    response_model=ResourceAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear recurso",
)
async def create_resource(
    org_id: str,
    payload: ResourceCreate,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.create_resource(db, org_id, payload)
    return resource


@router.get(
    "/{org_id}/admin/resources/{resource_id}",
    response_model=ResourceAdminRead,
    summary="Detalle recurso (Admin)",
)
async def get_resource_admin(
    org_id: str,
    resource_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_admin(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")
    return resource


@router.patch(
    "/{org_id}/admin/resources/{resource_id}",
    response_model=ResourceAdminRead,
    summary="Actualizar recurso",
)
async def update_resource(
    org_id: str,
    resource_id: UUID,
    payload: ResourceUpdate,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud.update_resource(db, resource_id, payload)
    if not updated:
        raise NotFoundError("Recurso")
    return updated


@router.delete(
    "/{org_id}/admin/resources/{resource_id}",
    summary="Eliminar recurso",
)
async def delete_resource(
    org_id: str,
    resource_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud.delete_resource(db, resource_id)
    if not deleted:
        raise NotFoundError("Recurso")
    return {"deleted_id": str(resource_id)}


@router.post(
    "/{org_id}/admin/resources/{resource_id}/publish",
    response_model=ResourceAdminRead,
    summary="Publicar recurso",
)
async def publish_resource(
    org_id: str,
    resource_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.publish_resource(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")
    return resource


@router.post(
    "/{org_id}/admin/resources/{resource_id}/unpublish",
    response_model=ResourceAdminRead,
    summary="Despublicar recurso",
)
async def unpublish_resource(
    org_id: str,
    resource_id: UUID,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.unpublish_resource(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")
    return resource


@router.post(
    "/{org_id}/admin/resources/{resource_id}/upload",
    response_model=ResourceAdminRead,
    summary="Subir archivo a un recurso",
)
async def upload_resource_file(
    org_id: str,
    resource_id: UUID,
    file: UploadFile = File(...),
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    resource = await crud.get_resource_admin(db, resource_id)
    if not resource:
        raise NotFoundError("Recurso")

    file_bytes = await file.read()
    storage_path = f"{org_id}/{resource_id}/{file.filename}"

    await db.storage.from_("resources").upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": file.content_type or "application/octet-stream"},
    )

    updated = await crud.update_storage_path(db, resource_id, storage_path)
    return updated
