import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from supabase_auth.errors import AuthApiError
from postgrest.exceptions import APIError as PostgRESTAPIError

from common.cache.redis_client import cache_ping
from common.exceptions import (
    OasisException,
    auth_api_error_handler,
    generic_exception_handler,
    oasis_exception_handler,
    postgrest_error_handler,
)
from services.analytics_service.api.v1.api import api_router as analytics_router
from services.auth_service.api.v1.api import api_router as auth_router, public_router
from services.gamification_service.api.v1.router import router as gamification_router
from services.journey_service.api.v1.api import api_router as journey_router
from services.resource_service.api.v1.router import router as resource_router
from services.crm_service.api.v1.api import api_router as crm_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oasis.gateway")

from common.rate_limit import limiter

app = FastAPI(
    title="OASIS Platform API",
    version="1.0.0",
    description="Gateway principal de la plataforma OASIS Multi-Tenant",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS middleware — restricted to known origins
# ---------------------------------------------------------------------------
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
app.include_router(public_router, prefix="/api/v1/public")
app.include_router(journey_router, prefix="/api/v1/journeys")
app.include_router(analytics_router, prefix="/api/v1/analytics")
app.include_router(gamification_router, prefix="/api/v1/gamification", tags=["Gamification"])
app.include_router(resource_router, prefix="/api/v1/resources", tags=["Resources"])
app.include_router(crm_router, prefix="/api/v1/crm", tags=["CRM"])


# ---------------------------------------------------------------------------
# Health check (includes Redis connectivity)
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    redis_ok = cache_ping()
    return {
        "status": "ok",
        "service": "oasis-gateway",
        "redis": "connected" if redis_ok else "unavailable",
    }
