from fastapi import APIRouter

from services.crm_service.api.v1.endpoints import contacts, notes, tasks, stats

api_router = APIRouter()

api_router.include_router(contacts.router, prefix="/contacts", tags=["CRM Contacts"])
api_router.include_router(notes.router, prefix="/notes", tags=["CRM Notes"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["CRM Tasks"])
api_router.include_router(stats.router, prefix="/stats", tags=["CRM Stats"])
