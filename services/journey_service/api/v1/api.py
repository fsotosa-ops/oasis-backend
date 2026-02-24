from fastapi import APIRouter

from services.journey_service.api.v1.endpoints import (
    admin_enrollments,
    admin_journey_organizations,
    admin_journeys,
    admin_steps,
    enrollments,
    journeys,
    user,
)

api_router = APIRouter()

# User-scoped routes must be registered before org-scoped routes to avoid
# path parameter conflicts (e.g. /me/... vs /{org_id}/...)
api_router.include_router(user.router, tags=["User Journeys"])
api_router.include_router(journeys.router, tags=["Journeys"])
api_router.include_router(admin_journeys.router, tags=["Admin Journeys"])
api_router.include_router(admin_steps.router, tags=["Admin Steps"])
api_router.include_router(admin_journey_organizations.router, tags=["Admin Journey Organizations"])
api_router.include_router(enrollments.router, prefix="/enrollments", tags=["Enrollments"])
api_router.include_router(admin_enrollments.router, tags=["Admin Enrollments"])
