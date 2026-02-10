from fastapi import APIRouter

from services.resource_service.api.v1.endpoints import (
    admin_resource_organizations,
    admin_resources,
    participant_resources,
)

router = APIRouter()

router.include_router(admin_resources.router, tags=["Resources - Admin"])
router.include_router(admin_resource_organizations.router, tags=["Resources - Admin Organizations"])
router.include_router(participant_resources.router, tags=["Resources - Participant"])
