from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

from common.events.schemas import RealtimeEvent

logger = logging.getLogger("oasis.events.manager")


class ConnectionManager:
    """Per-pod registry of active WebSocket connections, keyed by org_id.

    Thread-safety: asyncio.Lock guards all mutation; I/O (send) happens
    outside the lock to avoid holding it while awaiting network ops.
    """

    def __init__(self) -> None:
        self._connections: defaultdict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, org_ids: list[str]) -> None:
        async with self._lock:
            for org_id in org_ids:
                self._connections[org_id].add(ws)
        logger.debug("WS connected — orgs: %s", org_ids)

    async def disconnect(self, ws: WebSocket, org_ids: list[str]) -> None:
        async with self._lock:
            for org_id in org_ids:
                self._connections[org_id].discard(ws)
                if not self._connections[org_id]:
                    del self._connections[org_id]
        logger.debug("WS disconnected — orgs: %s", org_ids)

    async def broadcast_to_org(self, org_id: str, event: RealtimeEvent) -> None:
        payload = event.model_dump_json()
        async with self._lock:
            targets = set(self._connections.get(org_id, set()))

        if not targets:
            return

        dead: set[WebSocket] = set()
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[org_id].discard(ws)

    async def broadcast_all(self, event: RealtimeEvent) -> None:
        payload = event.model_dump_json()
        async with self._lock:
            all_ws = {
                ws
                for connections in self._connections.values()
                for ws in connections
            }

        for ws in all_ws:
            try:
                await ws.send_text(payload)
            except Exception:
                pass  # Stale connections cleaned up on next targeted broadcast


manager = ConnectionManager()
