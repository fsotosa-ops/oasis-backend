import logging

from fastapi import FastAPI
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
from services.auth_service.api.v1.api import api_router as auth_router
from services.journey_service.api.v1.api import api_router as journey_router

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


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "oasis-gateway"}
