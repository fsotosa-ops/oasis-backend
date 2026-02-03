import logging

from fastapi import FastAPI

from common.exceptions import OasisException, oasis_exception_handler
from services.auth_service.api.v1.api import api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth_service")

app = FastAPI(
    title="OASIS Auth Service",
    version="1.0.0",
    description="Servicio de Identidad Multi-Tenant con Supabase (standalone dev)",
)

# Handler para excepciones propias (standalone mode)
app.add_exception_handler(OasisException, oasis_exception_handler)

# Rutas
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "auth-service"}
