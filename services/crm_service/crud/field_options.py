from typing import Optional
from uuid import UUID

from supabase import AsyncClient

from common.cache.redis_client import cache_delete, cache_get_json, cache_set_json
from ..schemas.contacts import FieldOptionCreate, FieldOptionUpdate

_FIELD_OPTIONS_CACHE_KEY = "field_options:active"
_FIELD_OPTIONS_CACHE_TTL = 900  # 15 minutes


def _invalidate_cache() -> None:
    cache_delete(_FIELD_OPTIONS_CACHE_KEY)


async def list_field_options(
    db: AsyncClient,
    field_name: Optional[str] = None,
    include_inactive: bool = False,
) -> list[dict]:
    # Only cache the default query (active, no field filter) — the one the wizard uses
    use_cache = not field_name and not include_inactive
    if use_cache:
        cached = cache_get_json(_FIELD_OPTIONS_CACHE_KEY)
        if cached is not None:
            return cached

    query = db.schema("crm").table("field_options").select("*")
    if field_name:
        query = query.eq("field_name", field_name)
    if not include_inactive:
        query = query.eq("is_active", True)
    query = query.order("field_name").order("sort_order")
    result = await query.execute()
    data = result.data or []

    if use_cache:
        cache_set_json(_FIELD_OPTIONS_CACHE_KEY, data, _FIELD_OPTIONS_CACHE_TTL)

    return data


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
    _invalidate_cache()
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
    _invalidate_cache()
    return result.data[0] if result.data else None


async def delete_field_option(db: AsyncClient, option_id: str) -> bool:
    await (
        db.schema("crm")
        .table("field_options")
        .delete()
        .eq("id", option_id)
        .execute()
    )
    _invalidate_cache()
    return True