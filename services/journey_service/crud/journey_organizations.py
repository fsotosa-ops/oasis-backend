from uuid import UUID

from supabase import AsyncClient


async def get_assigned_orgs(
    db: AsyncClient,
    journey_id: UUID,
) -> list[dict]:
    response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .select("*")
        .eq("journey_id", str(journey_id))
        .order("assigned_at", desc=True)
        .execute()
    )
    return response.data or []


async def assign_journey_to_orgs(
    db: AsyncClient,
    journey_id: UUID,
    org_ids: list[UUID],
    assigned_by: UUID,
) -> list[dict]:
    payload = [
        {
            "journey_id": str(journey_id),
            "organization_id": str(org_id),
            "assigned_by": str(assigned_by),
        }
        for org_id in org_ids
    ]

    response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .upsert(payload, on_conflict="journey_id,organization_id")
        .execute()
    )
    return response.data or []


async def unassign_journey_from_orgs(
    db: AsyncClient,
    journey_id: UUID,
    org_ids: list[UUID],
) -> int:
    str_ids = [str(oid) for oid in org_ids]
    response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .delete()
        .eq("journey_id", str(journey_id))
        .in_("organization_id", str_ids)
        .execute()
    )
    return len(response.data) if response.data else 0


async def is_journey_assigned_to_org(
    db: AsyncClient,
    journey_id: UUID,
    org_id: str,
) -> bool:
    response = (
        await db.schema("journeys")
        .table("journey_organizations")
        .select("id")
        .eq("journey_id", str(journey_id))
        .eq("organization_id", org_id)
        .execute()
    )
    return len(response.data) > 0 if response.data else False
