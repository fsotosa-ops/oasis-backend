from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from common.auth.security import verify_token
from common.database.client import get_admin_client
from common.events.connection_manager import manager

logger = logging.getLogger("oasis.events.ws")

router = APIRouter(tags=["Realtime"])

# Keepalive interval — client must send "ping" within this window.
# Set below Cloud Run's 60-second idle-connection timeout.
_PING_WINDOW = 35  # seconds


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(..., description="Supabase JWT"),
) -> None:
    """WebSocket endpoint for real-time event streaming.

    Authentication: pass the Supabase access token as ?token=<jwt>.
    Protocol: client sends "ping" every 30s; server replies "pong".
    Events: JSON-serialised RealtimeEvent objects pushed by the server.
    """
    # --- Validate JWT; accept + close with 4001 so the client sees auth failure ---
    try:
        user = await verify_token(token)
    except Exception:
        await ws.accept()
        await ws.close(code=4001, reason="Unauthorized")
        return

    # --- Resolve org memberships (admin client bypasses RLS for this read) ---
    org_ids: list[str] = []
    try:
        db = await get_admin_client()
        resp = (
            await db.table("organization_members")
            .select("organization_id")
            .eq("user_id", str(user.id))
            .execute()
        )
        org_ids = [m["organization_id"] for m in (resp.data or [])]
    except Exception:
        logger.exception("Failed to fetch org memberships for user %s", user.id)

    await ws.accept()
    await manager.connect(ws, org_ids)
    logger.info("WS opened: user=%s orgs=%s", user.id, org_ids)

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=_PING_WINDOW)
                if data == "ping":
                    await ws.send_text("pong")
            except asyncio.TimeoutError:
                # Client stopped sending pings — close gracefully
                logger.info("WS ping timeout: user=%s", user.id)
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unexpected WS error: user=%s", user.id)
    finally:
        await manager.disconnect(ws, org_ids)
        logger.info("WS closed: user=%s", user.id)
