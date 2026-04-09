from __future__ import annotations

import logging

from supabase import AsyncClient

from common.database.client import get_admin_client
from common.exceptions import NotFoundError

logger = logging.getLogger("oasis.event_manager")


class EventManager:

    # ------------------------------------------------------------------
    # Events CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def list_org_events(db: AsyncClient, org_id: str) -> list[dict]:
        """Lista eventos de la organización con journey_ids y conteo de asistentes."""
        response = (
            await db.schema("crm").table("org_events")
            .select("*, event_journeys(journey_id), event_attendances(id)")
            .eq("organization_id", org_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [EventManager._flatten_event(row) for row in (response.data or [])]

    @staticmethod
    async def get_event(db: AsyncClient, org_id: str, event_id: str) -> dict:
        """Obtiene un evento verificando que pertenece a la org."""
        response = (
            await db.schema("crm").table("org_events")
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
    async def create_event(db: AsyncClient, org_id: str, data: dict) -> dict:
        """Crea un evento para la organización."""
        payload = {**data, "organization_id": org_id}
        response = (
            await db.schema("crm").table("org_events")
            .insert(payload)
            .execute()
        )
        row = response.data[0]
        row["journey_ids"] = []
        row["attendance_count"] = 0
        return row

    @staticmethod
    async def update_event(db: AsyncClient, org_id: str, event_id: str, data: dict) -> dict:
        """Actualiza un evento."""
        response = (
            await db.schema("crm").table("org_events")
            .update(data)
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .execute()
        )
        if not response.data:
            raise NotFoundError("Evento")
        return await EventManager.get_event(db, org_id, event_id)

    @staticmethod
    async def delete_event(db: AsyncClient, org_id: str, event_id: str) -> None:
        """Elimina un evento (CASCADE elimina event_journeys y event_attendances)."""
        await (
            db.schema("crm").table("org_events")
            .delete()
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .execute()
        )

    # ------------------------------------------------------------------
    # Event ↔ Journey assignment
    # ------------------------------------------------------------------

    @staticmethod
    async def list_event_journeys(db: AsyncClient, event_id: str) -> list[dict]:
        """Lista los journeys asignados a un evento."""
        response = (
            await db.schema("crm").table("event_journeys")
            .select("*")
            .eq("event_id", event_id)
            .execute()
        )
        return response.data or []

    @staticmethod
    async def add_journey_to_event(db: AsyncClient, event_id: str, journey_id: str) -> dict:
        """Asigna un journey a un evento."""
        response = (
            await db.schema("crm").table("event_journeys")
            .insert({"event_id": event_id, "journey_id": journey_id})
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def remove_journey_from_event(db: AsyncClient, event_id: str, journey_id: str) -> None:
        """Desasigna un journey de un evento."""
        await (
            db.schema("crm").table("event_journeys")
            .delete()
            .eq("event_id", event_id)
            .eq("journey_id", journey_id)
            .execute()
        )

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------

    @staticmethod
    async def list_attendances(event_id: str) -> list[dict]:
        """Lista asistentes de un evento con datos del perfil.

        Hace dos queries (attendances + profiles) en lugar de un PostgREST embed
        porque el FK `crm.event_attendances.user_id → public.profiles(id)` es
        cross-schema, y PostgREST no expone esa relación en el schema cache —
        el embed `profiles!event_attendances_user_id_fkey(...)` falla con
        "Could not find a relationship between 'event_attendances' and 'profiles'".
        Mismo patrón usado en journey_service/crud/journeys.py:758-764.
        """
        admin = await get_admin_client()

        # 1. Fetch attendances
        att_resp = (
            await admin.schema("crm").table("event_attendances")
            .select("*")
            .eq("event_id", event_id)
            .order("registered_at", desc=False)
            .execute()
        )
        rows = att_resp.data or []
        if not rows:
            return []

        # 2. Fetch profiles by user_id (separate query — public schema)
        user_ids = list({row["user_id"] for row in rows})
        prof_resp = (
            await admin.table("profiles")
            .select("id, email, full_name")
            .in_("id", user_ids)
            .execute()
        )
        profiles_by_id = {p["id"]: p for p in (prof_resp.data or [])}

        # 3. Merge profile fields onto each attendance row
        for row in rows:
            profile = profiles_by_id.get(row["user_id"], {})
            row["user_email"] = profile.get("email")
            row["user_full_name"] = profile.get("full_name")
        return rows

    @staticmethod
    async def register_attendance(db: AsyncClient, event_id: str, data: dict) -> dict:
        """Registra un asistente al evento (admin lo registra manualmente)."""
        payload = {**data, "event_id": event_id}
        if "user_id" in payload:
            payload["user_id"] = str(payload["user_id"])
        response = (
            await db.schema("crm").table("event_attendances")
            .insert(payload)
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def update_attendance(db: AsyncClient, attendance_id: str, data: dict) -> dict:
        """Actualiza el status o modalidad de un registro de asistencia."""
        response = (
            await db.schema("crm").table("event_attendances")
            .update(data)
            .eq("id", attendance_id)
            .execute()
        )
        if not response.data:
            raise NotFoundError("Asistencia")
        return response.data[0]

    @staticmethod
    async def remove_attendance(db: AsyncClient, attendance_id: str) -> None:
        """Elimina un registro de asistencia."""
        await (
            db.schema("crm").table("event_attendances")
            .delete()
            .eq("id", attendance_id)
            .execute()
        )

    @staticmethod
    async def get_event_journey_ids(event_id: str) -> list[str]:
        """Devuelve los journey_ids vinculados a un evento (fresh client, sin RLS)."""
        from supabase import acreate_client
        import os
        client = await acreate_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        )
        resp = (
            await client.schema("crm").table("event_journeys")
            .select("journey_id")
            .eq("event_id", event_id)
            .execute()
        )
        result = [ej["journey_id"] for ej in (resp.data or [])]
        print(f"[get_event_journey_ids] event={event_id} result={result} raw={resp.data}")
        return result

    # ------------------------------------------------------------------
    # Dashboard Summary
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard_summary(db: AsyncClient, org_id: str) -> dict:
        """Returns aggregated event metrics for the admin dashboard."""
        response = (
            await db.schema("crm").table("org_events")
            .select("id, name, slug, status, start_date, end_date, location, expected_participants, event_attendances(status, modality)")
            .eq("organization_id", org_id)
            .eq("is_active", True)
            .in_("status", ["live", "upcoming"])
            .order("start_date", desc=False)
            .execute()
        )

        live_events = []
        upcoming_events = []
        total_registered = 0
        total_attended = 0

        for row in (response.data or []):
            attendances = row.pop("event_attendances", []) or []

            registered = sum(1 for a in attendances if a["status"] == "registered")
            attended = sum(1 for a in attendances if a["status"] == "attended")
            no_show = sum(1 for a in attendances if a["status"] == "no_show")

            modality_breakdown: dict[str, int] = {}
            for a in attendances:
                mod = a.get("modality", "presencial")
                modality_breakdown[mod] = modality_breakdown.get(mod, 0) + 1

            item = {
                **row,
                "registered_count": registered,
                "attended_count": attended,
                "no_show_count": no_show,
                "modality_breakdown": modality_breakdown,
            }

            if row["status"] == "live":
                live_events.append(item)
                total_registered += registered
                total_attended += attended
            else:
                upcoming_events.append(item)

        return {
            "live_events": live_events,
            "upcoming_events": upcoming_events[:5],
            "totals": {
                "total_registered": total_registered,
                "total_attended": total_attended,
            },
        }

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
