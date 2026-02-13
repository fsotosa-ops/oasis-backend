from typing import Optional
from uuid import UUID

from supabase import AsyncClient

from ..schemas.contacts import FieldOptionCreate, FieldOptionUpdate


async def list_field_options(
    db: AsyncClient,
    field_name: Optional[str] = None,
    include_inactive: bool = False,
) -> list[dict]:
    query = db.schema("crm").table("field_options").select("*")
    if field_name:
        query = query.eq("field_name", field_name)
    if not include_inactive:
        query = query.eq("is_active", True)
    query = query.order("field_name").order("sort_order")
    result = await query.execute()
    return result.data or []


async def create_field_option(
    db: AsyncClient,
    data: FieldOptionCreate,
) -> dict:
    result = (
        await db.schema("crm")
        .table("field_options")
        .insert(data.model_dump())
        .execute()
    )
    return result.data[0]


async def update_field_option(
    db: AsyncClient,
    option_id: str,
    data: FieldOptionUpdate,
) -> Optional[dict]:
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        result = (
            await db.schema("crm")
            .table("field_options")
            .select("*")
            .eq("id", option_id)
            .single()
            .execute()
        )
        return result.data
    result = (
        await db.schema("crm")
        .table("field_options")
        .update(update_data)
        .eq("id", option_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_field_option(db: AsyncClient, option_id: str) -> bool:
    await (
        db.schema("crm")
        .table("field_options")
        .delete()
        .eq("id", option_id)
        .execute()
    )
    return True