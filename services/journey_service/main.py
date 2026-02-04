import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.exceptions import OasisException, oasis_exception_handler
from services.journey_service.api.v1.api import api_router
from services.journey_service.core.config import PROJECT_NAME, VERSION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("journey_service")

app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION,
    description="Servicio de Journeys para la plataforma OASIS (standalone dev)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(OasisException, oasis_exception_handler)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "journey-service"}
