from supabase import AsyncClient


async def get_org_profile(db: AsyncClient, org_id: str) -> dict | None:
    """Obtiene el perfil CRM de una organización. Retorna None si no existe aún."""
    response = (
        await db.schema("crm")
        .table("organization_profiles")
        .select("*")
        .eq("org_id", org_id)
        .execute()
    )
    data = response.data
    if not data:
        return None
    return data[0]


async def upsert_org_profile(db: AsyncClient, org_id: str, data: dict) -> dict:
    """Crea o actualiza el perfil CRM de una organización (upsert por org_id)."""
    payload = {"org_id": org_id, **data}
    response = (
        await db.schema("crm")
        .table("organization_profiles")
        .upsert(payload, on_conflict="org_id")
        .execute()
    )
    return response.data[0]
