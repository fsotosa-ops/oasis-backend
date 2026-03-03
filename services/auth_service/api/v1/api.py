from fastapi import APIRouter

from services.auth_service.api.v1.endpoints import auth, events, organizations, public_events, users

api_router = APIRouter()
public_router = APIRouter()

api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(events.router, prefix="/organizations/{org_id}/events", tags=["Events"])

public_router.include_router(public_events.router, prefix="/events", tags=["Public Events"])
