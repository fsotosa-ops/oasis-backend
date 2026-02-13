from typing import Optional

from supabase import AsyncClient

from ..schemas.contacts import ContactUpdate


async def _enrich_contacts_with_orgs(
    db: AsyncClient, contacts: list[dict]
) -> list[dict]:
    """Enrich contacts with organization memberships and profile data."""
    if not contacts:
        return contacts

    user_ids = [c["user_id"] for c in contacts]

    # Fetch org memberships for all contacts in one query
    memberships_resp = (
        await db.table("organization_members")
        .select("user_id, organization_id, role, status, joined_at, organizations(name, slug)")
        .in_("user_id", user_ids)
        .execute()
    )

    # Fetch profile data (full_name, is_platform_admin) for all contacts
    profiles_resp = (
        await db.table("profiles")
        .select("id, full_name, is_platform_admin")
        .in_("id", user_ids)
        .execute()
    )

    # Build lookup maps
    memberships_by_user: dict[str, list[dict]] = {}
    for m in (memberships_resp.data or []):
        uid = m["user_id"]
        org = m.get("organizations") or {}
        memberships_by_user.setdefault(uid, []).append({
            "organization_id": m["organization_id"],
            "organization_name": org.get("name"),
            "organization_slug": org.get("slug"),
            "role": m["role"],
            "status": m["status"],
            "joined_at": m.get("joined_at"),
        })

    profiles_by_id: dict[str, dict] = {}
    for p in (profiles_resp.data or []):
        profiles_by_id[p["id"]] = p

    # Enrich each contact
    for contact in contacts:
        uid = contact["user_id"]
        contact["organizations"] = memberships_by_user.get(uid, [])
        profile = profiles_by_id.get(uid, {})
        contact["full_name"] = profile.get("full_name")
        contact["is_platform_admin"] = profile.get("is_platform_admin", False)

    return contacts


async def get_contacts(
    db: AsyncClient,
    organization_id: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
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

    if status:
        query = query.eq("status", status)

    query = query.order("last_seen_at", desc=True).range(offset, offset + limit - 1)
    result = await query.execute()

    contacts = result.data or []
    total = result.count or 0

    # Enrich with org memberships and profile data
    contacts = await _enrich_contacts_with_orgs(db, contacts)

    return contacts, total


async def get_contact_by_id(db: AsyncClient, user_id: str) -> Optional[dict]:
    result = (
        await db.schema("crm")
        .table("contacts")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not result.data:
        return None

    enriched = await _enrich_contacts_with_orgs(db, [result.data])
    return enriched[0]


async def contact_belongs_to_org(
    db: AsyncClient, user_id: str, organization_id: str
) -> bool:
    """Verifica que el contacto (user_id) sea miembro activo de la organización."""
    resp = (
        await db.table("organization_members")
        .select("id")
        .eq("user_id", user_id)
        .eq("organization_id", organization_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return bool(resp.data)


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
    if not result.data:
        return None

    enriched = await _enrich_contacts_with_orgs(db, [result.data[0]])
    return enriched[0]
