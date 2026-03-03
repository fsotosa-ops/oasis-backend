"""Public endpoints for org_events (no auth required).

Used by QR landing page and projection screen.
Routes are registered under /api/v1/public/events/...
"""
from fastapi import APIRouter

from services.auth_service.logic.event_manager import EventManager
from services.auth_service.schemas.events import PublicEventResponse

router = APIRouter()


@router.get("/{org_slug}/{event_slug}", response_model=PublicEventResponse)
async def get_public_event(org_slug: str, event_slug: str):
    """Obtiene un evento activo por slugs de organización y evento.

    Sin autenticación — datos mínimos para QR landing y proyección pública.
    Retorna journey_id para que el frontend sepa en qué journey inscribir al usuario.
    """
    event = await EventManager.get_public_event(org_slug, event_slug)
    return PublicEventResponse(
        id=event["id"],
        name=event["name"],
        slug=event["slug"],
        org_id=event["org_id"],
        org_slug=event["org_slug"],
        org_name=event["org_name"],
        description=event.get("description"),
        start_date=event.get("start_date"),
        end_date=event.get("end_date"),
        location=event.get("location"),
        status=event["status"],
        landing_config=event["landing_config"],
        journey_id=event.get("journey_id"),
    )
