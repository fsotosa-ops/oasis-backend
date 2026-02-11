from typing import Optional

from supabase import AsyncClient

from ..schemas.notes import NoteCreate, NoteUpdate


async def create_note(
    db: AsyncClient,
    contact_user_id: str,
    organization_id: str,
    author_id: str,
    note_in: NoteCreate,
) -> dict:
    data = note_in.model_dump()
    data["author_id"] = author_id
    data["contact_user_id"] = contact_user_id
    data["organization_id"] = organization_id

    result = await db.schema("crm").table("notes").insert(data).execute()
    return result.data[0]


async def get_notes_for_contact(
    db: AsyncClient,
    contact_user_id: str,
    organization_id: str,
) -> list[dict]:
    result = (
        await db.schema("crm")
        .table("notes")
        .select("*")
        .eq("contact_user_id", contact_user_id)
        .eq("organization_id", organization_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


async def get_note_by_id(db: AsyncClient, note_id: str) -> Optional[dict]:
    """Fetch a single note by id (for fetch-then-authorize pattern)."""
    result = (
        await db.schema("crm")
        .table("notes")
        .select("*")
        .eq("id", note_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def update_note(db: AsyncClient, note_id: str, note_in: NoteUpdate) -> Optional[dict]:
    data = note_in.model_dump(exclude_unset=True)
    if not data:
        return {}

    result = (
        await db.schema("crm")
        .table("notes")
        .update(data)
        .eq("id", note_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_note(db: AsyncClient, note_id: str) -> bool:
    result = (
        await db.schema("crm")
        .table("notes")
        .delete()
        .eq("id", note_id)
        .execute()
    )
    return len(result.data) > 0 if result.data else False


async def update_note_scoped(
    db: AsyncClient, note_id: str, organization_id: str, note_in: NoteUpdate
) -> Optional[dict]:
    """Update con filtro de organization_id para asegurar scope."""
    data = note_in.model_dump(exclude_unset=True)
    if not data:
        return {}
    result = (
        await db.schema("crm")
        .table("notes")
        .update(data)
        .eq("id", note_id)
        .eq("organization_id", organization_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_note_scoped(
    db: AsyncClient, note_id: str, organization_id: str
) -> bool:
    """Delete con filtro de organization_id para asegurar scope."""
    result = (
        await db.schema("crm")
        .table("notes")
        .delete()
        .eq("id", note_id)
        .eq("organization_id", organization_id)
        .execute()
    )
    return len(result.data) > 0 if result.data else False
