from uuid import UUID

from fastapi import APIRouter, Depends, Query

from common.auth.security import get_current_user
from common.database.client import get_admin_client
from supabase import AsyncClient

router = APIRouter()


@router.get("/", summary="Metricas agregadas del CRM")
async def get_crm_stats(
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    org_id = str(organization_id)

    # Count contacts in org
    members_resp = (
        await db.table("organization_members")
        .select("user_id", count="exact")
        .eq("organization_id", org_id)
        .eq("status", "active")
        .execute()
    )
    total_contacts = members_resp.count or 0

    # Task stats
    tasks_resp = (
        await db.schema("crm")
        .table("tasks")
        .select("status")
        .eq("organization_id", org_id)
        .execute()
    )
    tasks_data = tasks_resp.data or []
    tasks_pending = sum(1 for t in tasks_data if t["status"] == "pending")
    tasks_in_progress = sum(1 for t in tasks_data if t["status"] == "in_progress")
    tasks_completed = sum(1 for t in tasks_data if t["status"] == "completed")
    tasks_cancelled = sum(1 for t in tasks_data if t["status"] == "cancelled")

    # Notes count
    notes_resp = (
        await db.schema("crm")
        .table("notes")
        .select("id", count="exact")
        .eq("organization_id", org_id)
        .execute()
    )
    total_notes = notes_resp.count or 0

    return {
        "total_contacts": total_contacts,
        "total_notes": total_notes,
        "tasks": {
            "total": len(tasks_data),
            "pending": tasks_pending,
            "in_progress": tasks_in_progress,
            "completed": tasks_completed,
            "cancelled": tasks_cancelled,
        },
    }
