"""Endpoints for org_events, event_journeys and event_attendances.

Org-scoped routes:   /auth/organizations/{org_id}/events/...
Gateway route:       /auth/events/{event_id}
"""
from fastapi import APIRouter, Depends, status

from common.auth.security import CurrentUser, OrgContext, OrgRoleRequired, get_current_token
from services.auth_service.logic.event_manager import EventManager
from services.auth_service.schemas.events import (
    AttendanceCreate,
    AttendanceResponse,
    AttendanceUpdate,
    EventCreate,
    EventJourneyAdd,
    EventJourneyResponse,
    EventResponse,
    EventUpdate,
)

router = APIRouter()

# Gateway router — no org scope required, any authenticated user
event_gateway_router = APIRouter()


@event_gateway_router.get("/{event_id}", response_model=EventResponse)
async def get_event_by_id(
    event_id: str,
    current_user: CurrentUser,  # noqa: ARG001 — verifica autenticación
):
    """Obtiene info de un evento por ID (usado por QR gateway, no requiere org)."""
    return await EventManager.get_event_by_id(event_id)


# ---------------------------------------------------------------------------
# Events CRUD
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Event ↔ Journey assignment
# ---------------------------------------------------------------------------

@router.get("/{event_id}/journeys", response_model=list[EventJourneyResponse])
async def list_event_journeys(
    event_id: str,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Lista los journeys asignados a un evento."""
    return await EventManager.list_event_journeys(token, event_id)


@router.post(
    "/{event_id}/journeys",
    response_model=EventJourneyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_journey_to_event(
    event_id: str,
    data: EventJourneyAdd,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Asigna un journey a un evento."""
    return await EventManager.add_journey_to_event(token, event_id, str(data.journey_id))


@router.delete(
    "/{event_id}/journeys/{journey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_journey_from_event(
    event_id: str,
    journey_id: str,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Desasigna un journey de un evento."""
    await EventManager.remove_journey_from_event(token, event_id, journey_id)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@router.get("/{event_id}/attendances", response_model=list[AttendanceResponse])
async def list_attendances(
    event_id: str,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Lista los asistentes de un evento."""
    return await EventManager.list_attendances(token, event_id)


@router.post(
    "/{event_id}/attendances",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_attendance(
    event_id: str,
    data: AttendanceCreate,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Registra un asistente al evento (el admin registra manualmente)."""
    payload = data.model_dump(mode="json", exclude_unset=True)
    return await EventManager.register_attendance(token, event_id, payload)


@router.patch(
    "/{event_id}/attendances/{attendance_id}",
    response_model=AttendanceResponse,
)
async def update_attendance(
    event_id: str,  # noqa: ARG001 — validated by OrgRoleRequired
    attendance_id: str,
    data: AttendanceUpdate,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Actualiza status o modalidad de un registro (ej: marcar como 'attended')."""
    payload = data.model_dump(mode="json", exclude_unset=True)
    return await EventManager.update_attendance(token, attendance_id, payload)


@router.delete(
    "/{event_id}/attendances/{attendance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_attendance(
    event_id: str,  # noqa: ARG001
    attendance_id: str,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Elimina un registro de asistencia."""
    await EventManager.remove_attendance(token, attendance_id)
