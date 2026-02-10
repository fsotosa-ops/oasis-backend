from typing import Optional

from supabase import AsyncClient

from ..schemas.contacts import ContactUpdate


async def get_contacts(
    db: AsyncClient,
    organization_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = db.schema("crm").table("contacts").select("*", count="exact")

    if organization_id:
        # Get user_ids that are members of this org, then filter contacts
        members_resp = (
            await db.table("organization_members")
            .select("user_id")
            .eq("organization_id", organization_id)
            .eq("status", "active")
            .execute()
        )
        member_ids = [m["user_id"] for m in (members_resp.data or [])]
        if not member_ids:
            return [], 0
        query = query.in_("user_id", member_ids)

    if search:
        query = query.or_(
            f"email.ilike.%{search}%,"
            f"first_name.ilike.%{search}%,"
            f"last_name.ilike.%{search}%"
        )

    query = query.order("last_seen_at", desc=True).range(offset, offset + limit - 1)
    result = await query.execute()
    return result.data or [], result.count or 0


async def get_contact_by_id(db: AsyncClient, user_id: str) -> Optional[dict]:
    result = (
        await db.schema("crm")
        .table("contacts")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data


async def update_contact(db: AsyncClient, user_id: str, data: ContactUpdate) -> Optional[dict]:
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return await get_contact_by_id(db, user_id)

    result = (
        await db.schema("crm")
        .table("contacts")
        .update(update_data)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0] if result.data else None
