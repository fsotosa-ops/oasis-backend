from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import get_current_user, get_user_memberships
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.crm_service.crud import notes as crud_notes
from services.crm_service.dependencies import _check_platform_admin, _find_membership
from services.crm_service.schemas.notes import NoteResponse, NoteUpdate
from supabase import AsyncClient

router = APIRouter()


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    note_in: NoteUpdate,
    user=Depends(get_current_user),  # noqa: B008
    memberships: list[dict] = Depends(get_user_memberships),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    # Fetch the note first
    note = await crud_notes.get_note_by_id(db, str(note_id))
    if not note:
        raise NotFoundError("Note")

    org_id = note["organization_id"]
    is_pa = _check_platform_admin(user, memberships)

    # Platform admins can update any note (no org scope needed)
    if is_pa:
        updated = await crud_notes.update_note(db, str(note_id), note_in)
        if not updated:
            raise NotFoundError("Note")
        return updated

    # Non-admin: must be member of the note's org
    membership = _find_membership(memberships, org_id)
    if not membership:
        raise ForbiddenError("No eres miembro de esta organización")

    if membership["role"] not in ("facilitador", "admin", "owner"):
        raise ForbiddenError("Rol insuficiente para editar notas")

    updated = await crud_notes.update_note_scoped(
        db, str(note_id), org_id, note_in
    )
    if not updated:
        raise NotFoundError("Note")
    return updated


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: UUID,
    user=Depends(get_current_user),  # noqa: B008
    memberships: list[dict] = Depends(get_user_memberships),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    # Fetch the note first
    note = await crud_notes.get_note_by_id(db, str(note_id))
    if not note:
        raise NotFoundError("Note")

    org_id = note["organization_id"]
    is_pa = _check_platform_admin(user, memberships)

    # Platform admins can delete any note
    if is_pa:
        deleted = await crud_notes.delete_note(db, str(note_id))
        if not deleted:
            raise NotFoundError("Note")
        return

    # Non-admin: must be member of the note's org
    membership = _find_membership(memberships, org_id)
    if not membership:
        raise ForbiddenError("No eres miembro de esta organización")

    if membership["role"] not in ("facilitador", "admin", "owner"):
        raise ForbiddenError("Rol insuficiente para eliminar notas")

    deleted = await crud_notes.delete_note_scoped(db, str(note_id), org_id)
    if not deleted:
        raise NotFoundError("Note")
