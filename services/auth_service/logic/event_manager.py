from __future__ import annotations

import logging

from common.database.client import get_admin_client, get_scoped_client
from common.exceptions import NotFoundError

logger = logging.getLogger("oasis.event_manager")


class EventManager:

    @staticmethod
    async def list_org_events(token: str, org_id: str) -> list[dict]:
        """Lista todos los eventos de una organización."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("org_events")
            .select("*")
            .eq("organization_id", org_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    @staticmethod
    async def get_event(token: str, org_id: str, event_id: str) -> dict:
        """Obtiene un evento por ID (verifica que pertenece a la org)."""
        client = await get_scoped_client(token)
        response = (
            await client.schema("crm").table("org_events")
            .select("*")
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .single()
            .execute()
        )
        if not response.data:
            raise NotFoundError("Evento")
        return response.data

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
        return response.data[0]

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
        return response.data[0]

    @staticmethod
    async def delete_event(token: str, org_id: str, event_id: str) -> None:
        """Elimina un evento."""
        client = await get_scoped_client(token)
        await (
            client.schema("crm").table("org_events")
            .delete()
            .eq("id", event_id)
            .eq("organization_id", org_id)
            .execute()
        )

    @staticmethod
    async def get_public_event(org_slug: str, event_slug: str) -> dict:
        """Obtiene un evento activo por slugs de org y evento (sin auth).
        Hace JOIN con organizations para resolver los slugs."""
        admin = await get_admin_client()

        # Resolve org by slug
        org_response = (
            await admin.table("organizations")
            .select("id, name, slug")
            .eq("slug", org_slug)
            .single()
            .execute()
        )
        if not org_response.data:
            raise NotFoundError("Organización")

        org = org_response.data

        # Fetch the active event
        event_response = (
            await admin.schema("crm").table("org_events")
            .select("*")
            .eq("organization_id", org["id"])
            .eq("slug", event_slug)
            .eq("is_active", True)
            .single()
            .execute()
        )
        if not event_response.data:
            raise NotFoundError("Evento")

        event = event_response.data

        return {
            **event,
            "org_id": org["id"],
            "org_slug": org["slug"],
            "org_name": org["name"],
        }
