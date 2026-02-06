from fastapi import APIRouter

from services.analytics_service.api.v1.endpoints import superset

api_router = APIRouter()

api_router.include_router(superset.router, tags=["Analytics"])
