from __future__ import annotations

import logging

from common.database.client import get_admin_client, get_scoped_client
from common.exceptions import NotFoundError

logger = logging.getLogger("oasis.event_manager")


class EventManager:

    # ------------------------------------------------------------------
    # Events CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def list_org_events(token: str, org_id: str) -> list[dict]:
        """Lista eventos de la organización con journey_ids y conteo de asistentes."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("org_events")
            .select("*, event_journeys(journey_id), event_attendances(id)")
            .eq("organization_id", org_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [EventManager._flatten_event(row) for row in (response.data or [])]

    @staticmethod
    async def get_event(token: str, org_id: str, event_id: str) -> dict:
        """Obtiene un evento verificando que pertenece a la org."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("org_events")
            .select("*, event_journeys(journey_id), event_attendances(id)")
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .single()
            .execute()
        )
        if not response.data:
            raise NotFoundError("Evento")
        return EventManager._flatten_event(response.data)

    @staticmethod
    async def get_event_by_id(event_id: str) -> dict:
        """Obtiene un evento por ID (gateway — sin requerir membresía en la org)."""
        admin = await get_admin_client()
        response = (
            await admin.schema("crm").table("org_events")
            .select("*, event_journeys(journey_id), event_attendances(id)")
            .eq("id", event_id)
            .single()
            .execute()
        )
        if not response.data:
            raise NotFoundError("Evento")
        return EventManager._flatten_event(response.data)

    @staticmethod
    async def create_event(token: str, org_id: str, data: dict) -> dict:
        """Crea un evento para la organización."""
        client = await get_scoped_client(token)
        payload = {**data, "organization_id": org_id}
        response = (
            await client.schema("crm").table("org_events")
            .insert(payload)
            .execute()
        )
        row = response.data[0]
        row["journey_ids"] = []
        row["attendance_count"] = 0
        return row

    @staticmethod
    async def update_event(token: str, org_id: str, event_id: str, data: dict) -> dict:
        """Actualiza un evento."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("org_events")
            .update(data)
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .execute()
        )
        if not response.data:
            raise NotFoundError("Evento")
        return await EventManager.get_event(token, org_id, event_id)

    @staticmethod
    async def delete_event(token: str, org_id: str, event_id: str) -> None:
        """Elimina un evento (CASCADE elimina event_journeys y event_attendances)."""
        client = await get_scoped_client(token)
        await (
            client.schema("crm").table("org_events")
            .delete()
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .execute()
        )

    # ------------------------------------------------------------------
    # Event ↔ Journey assignment
    # ------------------------------------------------------------------

    @staticmethod
    async def list_event_journeys(token: str, event_id: str) -> list[dict]:
        """Lista los journeys asignados a un evento."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("event_journeys")
            .select("*")
            .eq("event_id", event_id)
            .execute()
        )
        return response.data or []

    @staticmethod
    async def add_journey_to_event(token: str, event_id: str, journey_id: str) -> dict:
        """Asigna un journey a un evento."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("event_journeys")
            .insert({"event_id": event_id, "journey_id": journey_id})
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def remove_journey_from_event(token: str, event_id: str, journey_id: str) -> None:
        """Desasigna un journey de un evento."""
        client = await get_scoped_client(token)
        await (
            client.schema("crm").table("event_journeys")
            .delete()
            .eq("event_id", event_id)
            .eq("journey_id", journey_id)
            .execute()
        )

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------

    @staticmethod
    async def list_attendances(token: str, event_id: str) -> list[dict]:
        """Lista asistentes de un evento con datos del perfil."""
        admin = await get_admin_client()
        response = (
            await admin.schema("crm").table("event_attendances")
            .select(
                "*, profiles!event_attendances_user_id_fkey(email, full_name)"
            )
            .eq("event_id", event_id)
            .order("registered_at", desc=False)
            .execute()
        )
        result = []
        for row in (response.data or []):
            profile = row.pop("profiles", None) or {}
            row["user_email"] = profile.get("email")
            row["user_full_name"] = profile.get("full_name")
            result.append(row)
        return result

    @staticmethod
    async def register_attendance(token: str, event_id: str, data: dict) -> dict:
        """Registra un asistente al evento (admin lo registra manualmente)."""
        client = await get_scoped_client(token)
        payload = {**data, "event_id": event_id}
        if "user_id" in payload:
            payload["user_id"] = str(payload["user_id"])
        response = (
            await client.schema("crm").table("event_attendances")
            .insert(payload)
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def update_attendance(token: str, attendance_id: str, data: dict) -> dict:
        """Actualiza el status o modalidad de un registro de asistencia."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("event_attendances")
            .update(data)
            .eq("id", attendance_id)
            .execute()
        )
        if not response.data:
            raise NotFoundError("Asistencia")
        return response.data[0]

    @staticmethod
    async def remove_attendance(token: str, attendance_id: str) -> None:
        """Elimina un registro de asistencia."""
        client = await get_scoped_client(token)
        await (
            client.schema("crm").table("event_attendances")
            .delete()
            .eq("id", attendance_id)
            .execute()
        )

    @staticmethod
    async def get_event_journey_ids(event_id: str) -> list[str]:
        """Devuelve los journey_ids vinculados a un evento (admin client, sin RLS)."""
        admin = await get_admin_client()
        resp = (
            await admin.schema("crm").table("event_journeys")
            .select("journey_id")
            .eq("event_id", event_id)
            .execute()
        )
        return [ej["journey_id"] for ej in (resp.data or [])]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_event(row: dict) -> dict:
        """Convierte los joins anidados de Supabase en campos planos."""
        journeys = row.pop("event_journeys", []) or []
        attendances = row.pop("event_attendances", []) or []
        row["journey_ids"] = [ej["journey_id"] for ej in journeys]
        row["attendance_count"] = len(attendances)
        return row
