from uuid import UUID

from supabase import AsyncClient

from services.resource_service.schemas.resources import ResourceCreate, ResourceUpdate


async def list_resources_admin(
    db: AsyncClient,
    org_id: str,
    is_published: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    query = (
        db.schema("resources").table("resources")
        .select("*", count="exact")
        .or_(
            f"organization_id.eq.{org_id},"
            f"id.in.(SELECT resource_id FROM resources.resource_organizations WHERE organization_id='{org_id}')"
        )
        .order("created_at", desc=True)
        .range(skip, skip + limit - 1)
    )

    if is_published is not None:
        query = query.eq("is_published", is_published)

    response = await query.execute()
    resources = response.data or []

    # Enrich with conditions count and consumption count
    for r in resources:
        conds = await _get_conditions(db, r["id"])
        r["unlock_conditions"] = conds

        cons_resp = (
            await db.schema("resources").table("resource_consumptions")
            .select("id", count="exact")
            .eq("resource_id", r["id"])
            .not_.is_("completed_at", "null")
            .execute()
        )
        r["consumption_count"] = cons_resp.count or 0

    return resources, response.count or 0


async def get_resource_admin(db: AsyncClient, resource_id: UUID) -> dict | None:
    response = (
        await db.schema("resources").table("resources")
        .select("*")
        .eq("id", str(resource_id))
        .single()
        .execute()
    )
    if not response.data:
        return None

    resource = response.data
    resource["unlock_conditions"] = await _get_conditions(db, str(resource_id))

    cons_resp = (
        await db.schema("resources").table("resource_consumptions")
        .select("id", count="exact")
        .eq("resource_id", str(resource_id))
        .not_.is_("completed_at", "null")
        .execute()
    )
    resource["consumption_count"] = cons_resp.count or 0

    return resource


async def create_resource(
    db: AsyncClient,
    org_id: str,
    payload: ResourceCreate,
) -> dict:
    resource_data = {
        "organization_id": org_id,
        "title": payload.title,
        "description": payload.description,
        "type": payload.type,
        "content_url": payload.content_url,
        "thumbnail_url": payload.thumbnail_url,
        "points_on_completion": payload.points_on_completion,
        "unlock_logic": payload.unlock_logic,
        "metadata": payload.metadata,
    }
    response = (
        await db.schema("resources").table("resources")
        .insert(resource_data)
        .execute()
    )
    resource = response.data[0] if response.data else {}
    resource_id = resource["id"]

    # Auto-assign owner org
    await db.schema("resources").table("resource_organizations").insert({
        "resource_id": resource_id,
        "organization_id": org_id,
    }).execute()

    # Insert unlock conditions
    if payload.unlock_conditions:
        conditions = [
            {
                "resource_id": resource_id,
                "condition_type": c.condition_type,
                "reference_id": str(c.reference_id) if c.reference_id else None,
                "reference_value": c.reference_value,
            }
            for c in payload.unlock_conditions
        ]
        await db.schema("resources").table("resource_unlock_conditions").insert(conditions).execute()

    resource["unlock_conditions"] = await _get_conditions(db, resource_id)
    resource["consumption_count"] = 0
    return resource


async def update_resource(
    db: AsyncClient,
    resource_id: UUID,
    payload: ResourceUpdate,
) -> dict | None:
    update_data = {}
    if payload.title is not None:
        update_data["title"] = payload.title
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.type is not None:
        update_data["type"] = payload.type
    if payload.content_url is not None:
        update_data["content_url"] = payload.content_url
    if payload.thumbnail_url is not None:
        update_data["thumbnail_url"] = payload.thumbnail_url
    if payload.points_on_completion is not None:
        update_data["points_on_completion"] = payload.points_on_completion
    if payload.unlock_logic is not None:
        update_data["unlock_logic"] = payload.unlock_logic
    if payload.metadata is not None:
        update_data["metadata"] = payload.metadata

    if update_data:
        response = (
            await db.schema("resources").table("resources")
            .update(update_data)
            .eq("id", str(resource_id))
            .execute()
        )
        if not response.data:
            return None

    # Replace unlock conditions if provided
    if payload.unlock_conditions is not None:
        await db.schema("resources").table("resource_unlock_conditions").delete().eq(
            "resource_id", str(resource_id)
        ).execute()

        if payload.unlock_conditions:
            conditions = [
                {
                    "resource_id": str(resource_id),
                    "condition_type": c.condition_type,
                    "reference_id": str(c.reference_id) if c.reference_id else None,
                    "reference_value": c.reference_value,
                }
                for c in payload.unlock_conditions
            ]
            await db.schema("resources").table("resource_unlock_conditions").insert(conditions).execute()

    return await get_resource_admin(db, resource_id)


async def delete_resource(db: AsyncClient, resource_id: UUID) -> bool:
    response = (
        await db.schema("resources").table("resources")
        .delete()
        .eq("id", str(resource_id))
        .execute()
    )
    return len(response.data) > 0 if response.data else False


async def publish_resource(db: AsyncClient, resource_id: UUID) -> dict | None:
    await (
        db.schema("resources").table("resources")
        .update({"is_published": True})
        .eq("id", str(resource_id))
        .execute()
    )
    return await get_resource_admin(db, resource_id)


async def unpublish_resource(db: AsyncClient, resource_id: UUID) -> dict | None:
    await (
        db.schema("resources").table("resources")
        .update({"is_published": False})
        .eq("id", str(resource_id))
        .execute()
    )
    return await get_resource_admin(db, resource_id)


async def update_storage_path(
    db: AsyncClient,
    resource_id: UUID,
    storage_path: str,
) -> dict | None:
    await (
        db.schema("resources").table("resources")
        .update({"storage_path": storage_path})
        .eq("id", str(resource_id))
        .execute()
    )
    return await get_resource_admin(db, resource_id)


async def list_resources_for_user(
    db: AsyncClient,
    user_org_ids: list[str],
) -> list[dict]:
    if not user_org_ids:
        return []

    org_filter = ",".join(user_org_ids)
    response = (
        await db.schema("resources").table("resources")
        .select("*")
        .eq("is_published", True)
        .or_(
            f"organization_id.in.({org_filter}),"
            f"id.in.(SELECT resource_id FROM resources.resource_organizations WHERE organization_id IN ({org_filter}))"
        )
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


async def get_resource_for_user(db: AsyncClient, resource_id: UUID) -> dict | None:
    response = (
        await db.schema("resources").table("resources")
        .select("*")
        .eq("id", str(resource_id))
        .eq("is_published", True)
        .single()
        .execute()
    )
    return response.data


# --- Helpers ---

async def _get_conditions(db: AsyncClient, resource_id: str) -> list[dict]:
    response = (
        await db.schema("resources").table("resource_unlock_conditions")
        .select("*")
        .eq("resource_id", resource_id)
        .order("created_at")
        .execute()
    )
    return response.data or []
