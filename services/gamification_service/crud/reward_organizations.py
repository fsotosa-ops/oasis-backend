from uuid import UUID

from supabase import AsyncClient


async def get_assigned_orgs(db: AsyncClient, reward_id: UUID) -> list[dict]:
    """Devuelve las organizaciones asignadas a una recompensa."""
    response = (
        await db.schema("journeys").table("reward_organizations")
        .select("id, reward_id, organization_id, assigned_at, organizations(id, name, slug)")
        .eq("reward_id", str(reward_id))
        .order("assigned_at")
        .execute()
    )
    rows = response.data or []
    # Aplanar la org anidada
    result = []
    for row in rows:
        org = row.pop("organizations", None) or {}
        result.append({**row, "org_name": org.get("name"), "org_slug": org.get("slug")})
    return result


async def assign_to_orgs(
    db: AsyncClient,
    reward_id: UUID,
    organization_ids: list[UUID],
    assigned_by: UUID | None = None,
) -> None:
    """Asigna la recompensa a las orgs indicadas (ignora duplicados)."""
    if not organization_ids:
        return
    rows = [
        {
            "reward_id": str(reward_id),
            "organization_id": str(org_id),
            **({"assigned_by": str(assigned_by)} if assigned_by else {}),
        }
        for org_id in organization_ids
    ]
    await (
        db.schema("journeys").table("reward_organizations")
        .upsert(rows, on_conflict="reward_id,organization_id")
        .execute()
    )


async def unassign_from_orgs(
    db: AsyncClient,
    reward_id: UUID,
    organization_ids: list[UUID],
) -> None:
    """Desasigna la recompensa de las orgs indicadas."""
    if not organization_ids:
        return
    await (
        db.schema("journeys").table("reward_organizations")
        .delete()
        .eq("reward_id", str(reward_id))
        .in_("organization_id", [str(o) for o in organization_ids])
        .execute()
    )
