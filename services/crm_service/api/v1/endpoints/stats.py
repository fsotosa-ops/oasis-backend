from fastapi import APIRouter, Depends

from common.database.client import get_admin_client
from services.crm_service.dependencies import CrmContext, CrmReadAccess
from supabase import AsyncClient

router = APIRouter()


@router.get("/", summary="Metricas agregadas del CRM")
async def get_crm_stats(
    ctx: CrmContext = Depends(CrmReadAccess),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
):
    org_id = ctx.organization_id

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

    # Contact breakdown by status
    contacts_resp = (
        await db.schema("crm")
        .table("contacts")
        .select("status")
        .eq("organization_id", org_id)
        .execute()
    )
    statuses = [c["status"] for c in (contacts_resp.data or [])]
    active_contacts = sum(1 for s in statuses if s == "active")
    inactive_contacts = sum(1 for s in statuses if s == "inactive")
    risk_contacts = sum(1 for s in statuses if s == "risk")

    return {
        "total_contacts": total_contacts,
        "active_contacts": active_contacts,
        "inactive_contacts": inactive_contacts,
        "risk_contacts": risk_contacts,
        "total_tasks": len(tasks_data),
        "pending_tasks": tasks_pending,
        "in_progress_tasks": tasks_in_progress,
        "completed_tasks": tasks_completed,
        "total_notes": total_notes,
    }
