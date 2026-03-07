"""Admin endpoints for org_events management.

All routes are org-scoped: /api/v1/auth/organizations/{org_id}/events/...
Requires owner or admin role in the organization.
"""
from fastapi import APIRouter, Depends, status

from common.auth.security import CurrentUser, OrgContext, OrgRoleRequired, get_current_token
from services.auth_service.logic.event_manager import EventManager
from services.auth_service.schemas.events import (
    EventCreate,
    EventResponse,
    EventUpdate,
)

router = APIRouter()

# Router no org-scoped: cualquier usuario autenticado puede consultar un evento por ID
event_gateway_router = APIRouter()


@event_gateway_router.get("/{event_id}", response_model=EventResponse)
async def get_event_by_id(
    event_id: str,
    current_user: CurrentUser,  # noqa: ARG001 — solo verifica autenticación
):
    """Obtiene info básica de un evento por ID (usado por el gateway del evento)."""
    return await EventManager.get_event_by_id(event_id)


@router.get("", response_model=list[EventResponse])
async def list_events(
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Lista todos los eventos de la organización."""
    return await EventManager.list_org_events(token, org.organization_id)


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    data: EventCreate,
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Crea un evento para la organización."""
    # mode='json' serializes UUIDs → str, datetimes → ISO str, nested models → dict
    payload = data.model_dump(mode="json", exclude_unset=True)
    return await EventManager.create_event(token, org.organization_id, payload)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Obtiene el detalle de un evento."""
    return await EventManager.get_event(token, org.organization_id, event_id)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    data: EventUpdate,
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Actualiza un evento."""
    payload = data.model_dump(mode="json", exclude_unset=True)
    return await EventManager.update_event(token, org.organization_id, event_id, payload)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Elimina un evento."""
    await EventManager.delete_event(token, org.organization_id, event_id)
