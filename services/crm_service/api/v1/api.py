from fastapi import APIRouter

from services.crm_service.api.v1.endpoints import contacts, field_options, notes, tasks, stats, org_profiles

api_router = APIRouter()

api_router.include_router(contacts.router, prefix="/contacts", tags=["CRM Contacts"])
api_router.include_router(notes.router, prefix="/notes", tags=["CRM Notes"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["CRM Tasks"])
api_router.include_router(stats.router, prefix="/stats", tags=["CRM Stats"])
api_router.include_router(field_options.router, prefix="/field-options", tags=["CRM Field Options"])
api_router.include_router(org_profiles.router, prefix="/org-profiles", tags=["CRM Org Profiles"])
