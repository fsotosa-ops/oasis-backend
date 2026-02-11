from typing import Optional

from supabase import AsyncClient

from ..schemas.tasks import TaskCreate, TaskUpdate


async def create_task(
    db: AsyncClient,
    contact_user_id: str,
    organization_id: str,
    creator_id: str,
    task_in: TaskCreate,
) -> dict:
    data = task_in.model_dump()
    data["created_by"] = creator_id
    data["contact_user_id"] = contact_user_id
    data["organization_id"] = organization_id
    if data.get("assigned_to"):
        data["assigned_to"] = str(data["assigned_to"])
    if data.get("due_date"):
        data["due_date"] = data["due_date"].isoformat()

    result = await db.schema("crm").table("tasks").insert(data).execute()
    return result.data[0]


async def get_tasks_for_contact(
    db: AsyncClient,
    contact_user_id: str,
    organization_id: str,
) -> list[dict]:
    result = (
        await db.schema("crm")
        .table("tasks")
        .select("*")
        .eq("contact_user_id", contact_user_id)
        .eq("organization_id", organization_id)
        .order("due_date", desc=False)
        .execute()
    )
    return result.data or []


async def get_tasks_global(
    db: AsyncClient,
    organization_id: str,
    assigned_to: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = (
        db.schema("crm")
        .table("tasks")
        .select("*", count="exact")
        .eq("organization_id", organization_id)
    )

    if assigned_to:
        query = query.eq("assigned_to", assigned_to)
    if status:
        query = query.eq("status", status)

    query = query.order("due_date", desc=False).range(offset, offset + limit - 1)
    result = await query.execute()
    return result.data or [], result.count or 0


async def get_task_by_id(db: AsyncClient, task_id: str) -> Optional[dict]:
    """Fetch a single task by id (for fetch-then-authorize pattern)."""
    result = (
        await db.schema("crm")
        .table("tasks")
        .select("*")
        .eq("id", task_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def update_task(db: AsyncClient, task_id: str, task_in: TaskUpdate) -> Optional[dict]:
    data = task_in.model_dump(exclude_unset=True)
    if not data:
        return {}

    if data.get("assigned_to"):
        data["assigned_to"] = str(data["assigned_to"])
    if data.get("due_date"):
        data["due_date"] = data["due_date"].isoformat()

    result = (
        await db.schema("crm")
        .table("tasks")
        .update(data)
        .eq("id", task_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_task(db: AsyncClient, task_id: str) -> bool:
    result = (
        await db.schema("crm")
        .table("tasks")
        .delete()
        .eq("id", task_id)
        .execute()
    )
    return len(result.data) > 0 if result.data else False


async def update_task_scoped(
    db: AsyncClient, task_id: str, organization_id: str, task_in: TaskUpdate
) -> Optional[dict]:
    """Update con filtro de organization_id para asegurar scope."""
    data = task_in.model_dump(exclude_unset=True)
    if not data:
        return {}
    if data.get("assigned_to"):
        data["assigned_to"] = str(data["assigned_to"])
    if data.get("due_date"):
        data["due_date"] = data["due_date"].isoformat()
    result = (
        await db.schema("crm")
        .table("tasks")
        .update(data)
        .eq("id", task_id)
        .eq("organization_id", organization_id)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_task_scoped(
    db: AsyncClient, task_id: str, organization_id: str
) -> bool:
    """Delete con filtro de organization_id para asegurar scope."""
    result = (
        await db.schema("crm")
        .table("tasks")
        .delete()
        .eq("id", task_id)
        .eq("organization_id", organization_id)
        .execute()
    )
    return len(result.data) > 0 if result.data else False
