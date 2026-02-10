from uuid import UUID

from supabase import AsyncClient


async def get_assigned_orgs(
    db: AsyncClient,
    resource_id: UUID,
) -> list[dict]:
    response = (
        await db.schema("resources")
        .table("resource_organizations")
        .select("*")
        .eq("resource_id", str(resource_id))
        .order("assigned_at", desc=True)
        .execute()
    )
    return response.data or []


async def assign_resource_to_orgs(
    db: AsyncClient,
    resource_id: UUID,
    org_ids: list[UUID],
    assigned_by: UUID,
) -> list[dict]:
    payload = [
        {
            "resource_id": str(resource_id),
            "organization_id": str(org_id),
            "assigned_by": str(assigned_by),
        }
        for org_id in org_ids
    ]

    response = (
        await db.schema("resources")
        .table("resource_organizations")
        .upsert(payload, on_conflict="resource_id,organization_id")
        .execute()
    )
    return response.data or []


async def unassign_resource_from_orgs(
    db: AsyncClient,
    resource_id: UUID,
    org_ids: list[UUID],
) -> int:
    str_ids = [str(oid) for oid in org_ids]
    response = (
        await db.schema("resources")
        .table("resource_organizations")
        .delete()
        .eq("resource_id", str(resource_id))
        .in_("organization_id", str_ids)
        .execute()
    )
    return len(response.data) if response.data else 0
