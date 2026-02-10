from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import get_current_user
from common.database.client import get_admin_client
from common.exceptions import NotFoundError
from services.crm_service.crud import notes as crud_notes
from services.crm_service.schemas.notes import NoteResponse, NoteUpdate
from supabase import AsyncClient

router = APIRouter()


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    note_in: NoteUpdate,
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    updated = await crud_notes.update_note(db, str(note_id), note_in)
    if not updated:
        raise NotFoundError("Note")
    return updated


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: UUID,
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    deleted = await crud_notes.delete_note(db, str(note_id))
    if not deleted:
        raise NotFoundError("Note")
