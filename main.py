import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from supabase_auth.errors import AuthApiError
from postgrest.exceptions import APIError as PostgRESTAPIError

from common.exceptions import (
    OasisException,
    auth_api_error_handler,
    generic_exception_handler,
    oasis_exception_handler,
    postgrest_error_handler,
)
from services.analytics_service.api.v1.api import api_router as analytics_router
from services.auth_service.api.v1.api import api_router as auth_router
from services.gamification_service.api.v1.router import router as gamification_router
from services.journey_service.api.v1.api import api_router as journey_router
from services.resource_service.api.v1.router import router as resource_router
from services.crm_service.api.v1.api import api_router as crm_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oasis.gateway")

app = FastAPI(
    title="OASIS Platform API",
    version="1.0.0",
    description="Gateway principal de la plataforma OASIS Multi-Tenant",
)

# ---------------------------------------------------------------------------
# CORS middleware (global, unico lugar)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware: propagar X-Forwarded-Proto para que FastAPI genere URLs HTTPS
# en redirects 307 (trailing slash) cuando esta detras de Cloud Run / proxy.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def set_scheme_from_proxy(request: Request, call_next):
    proto = request.headers.get("x-forwarded-proto")
    if proto:
        request.scope["scheme"] = proto
    return await call_next(request)


# ---------------------------------------------------------------------------
# Exception handlers globales (aplican a todos los routers incluidos)
# ---------------------------------------------------------------------------
app.add_exception_handler(OasisException, oasis_exception_handler)
app.add_exception_handler(AuthApiError, auth_api_error_handler)
app.add_exception_handler(PostgRESTAPIError, postgrest_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# ---------------------------------------------------------------------------
# Routers (include_router, NO mount — los handlers del parent propagan)
# ---------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(journey_router, prefix="/api/v1/journeys")
app.include_router(analytics_router, prefix="/api/v1/analytics")
app.include_router(gamification_router, prefix="/api/v1/gamification", tags=["Gamification"])
app.include_router(resource_router, prefix="/api/v1/resources", tags=["Resources"])
app.include_router(crm_router, prefix="/api/v1/crm", tags=["CRM"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "oasis-gateway"}
