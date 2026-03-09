"""Endpoints for org_events, event_journeys and event_attendances.

Org-scoped routes:   /auth/organizations/{org_id}/events/...
Gateway route:       /auth/events/{event_id}
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from common.auth.security import CurrentUser, OrgContext, OrgRoleRequired, get_current_token
from common.database.client import get_admin_client
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
    JoinEventResponse,
)

logger = logging.getLogger("oasis.events")

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


@event_gateway_router.post("/{event_id}/join", response_model=JoinEventResponse)
async def join_event(
    event_id: str,
    current_user: CurrentUser,
):
    """Unified join flow: org membership + attendance + enrollment (if journey assigned)."""
    admin = await get_admin_client()
    user_id = str(current_user.id)
    now = datetime.now(timezone.utc).isoformat()

    # 1. Fetch event + its journey assignments
    event_resp = (
        await admin.schema("crm").table("org_events")
        .select("*")
        .eq("id", event_id)
        .single()
        .execute()
    )
    if not event_resp.data:
        from common.exceptions import NotFoundError
        raise NotFoundError("Evento")

    event = event_resp.data
    org_id = event["organization_id"]
    journey_ids = await EventManager.get_event_journey_ids(event_id)
    print(f"[join_event] event={event_id} org={org_id} journey_ids={journey_ids}")

    org_joined = False
    attendance_registered = False
    journey_enrolled: str | None = None

    # 2. Upsert organization_members (auto-join org as participante)
    try:
        await admin.schema("public").table("organization_members").upsert(
            {
                "organization_id": org_id,
                "user_id": user_id,
                "role": "participante",
                "status": "active",
                "joined_at": now,
            },
            on_conflict="organization_id,user_id",
        ).execute()
        org_joined = True
        logger.info("join_event: user %s joined org %s", user_id, org_id)
    except Exception:
        logger.warning("join_event: failed to upsert org membership for user %s", user_id)

    # 3. Upsert crm.event_attendances (status=registered, modality=presencial)
    try:
        await admin.schema("crm").table("event_attendances").upsert(
            {
                "event_id": event_id,
                "user_id": user_id,
                "status": "registered",
                "modality": "presencial",
                "registered_at": now,
            },
            on_conflict="event_id,user_id",
        ).execute()
        attendance_registered = True
        logger.info("join_event: attendance registered for user %s event %s", user_id, event_id)
    except Exception:
        logger.warning("join_event: failed to upsert attendance for user %s event %s", user_id, event_id)

    # 4. If event has journeys → enroll in first journey (skip if already enrolled)
    if journey_ids:
        first_journey_id = journey_ids[0]
        try:
            existing = (
                await admin.schema("journeys").table("enrollments")
                .select("id")
                .eq("user_id", user_id)
                .eq("journey_id", first_journey_id)
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if not existing.data:
                await admin.schema("journeys").table("enrollments").insert(
                    {
                        "user_id": user_id,
                        "journey_id": first_journey_id,
                        "event_id": event_id,
                        "status": "active",
                        "current_step_index": 0,
                        "started_at": now,
                    }
                ).execute()
                logger.info("join_event: enrolled user %s in journey %s", user_id, first_journey_id)
            else:
                logger.info("join_event: user %s already enrolled in journey %s", user_id, first_journey_id)
            # Always return the journey ID so the frontend can redirect
            journey_enrolled = first_journey_id
        except Exception as exc:
            logger.exception("join_event: failed to enroll user %s in journey %s: %s", user_id, first_journey_id, exc)

    print(f"[join_event] RESPONSE journey_enrolled={journey_enrolled}")
    return JoinEventResponse(
        event_id=event_id,
        organization_id=org_id,
        org_joined=org_joined,
        attendance_registered=attendance_registered,
        journey_enrolled=journey_enrolled,
    )


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
