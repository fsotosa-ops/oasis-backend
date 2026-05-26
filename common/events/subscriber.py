from __future__ import annotations

import asyncio
import logging
import os

from common.events.connection_manager import manager
from common.events.schemas import RealtimeEvent

logger = logging.getLogger("oasis.events.subscriber")

CHANNEL = "platform:events"


async def start_subscriber() -> None:
    """Long-running background task: subscribes to Redis pub/sub and
    dispatches incoming events to the ConnectionManager for WebSocket
    broadcast to all connected clients in the relevant org.

    Auto-reconnects with exponential backoff on any failure.
    Exits cleanly on asyncio.CancelledError (FastAPI lifespan shutdown).
    """
    backoff = 1.0

    while True:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.warning("REDIS_URL not set — realtime subscriber disabled")
            return

        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=65,  # > 60s to survive Cloud Run keepalive gaps
                health_check_interval=30,
            )
            async with client.pubsub() as pubsub:
                await pubsub.subscribe(CHANNEL)
                backoff = 1.0
                logger.info("Subscriber connected — listening on '%s'", CHANNEL)

                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    await _dispatch(message["data"])

        except asyncio.CancelledError:
            logger.info("Subscriber task cancelled — shutting down")
            return
        except Exception:
            logger.exception(
                "Subscriber crashed, reconnecting in %.1fs", backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


async def _dispatch(raw: str) -> None:
    try:
        event = RealtimeEvent.model_validate_json(raw)
    except Exception:
        logger.warning("Malformed event received (%.200s)", raw)
        return

    if event.org_id:
        await manager.broadcast_to_org(event.org_id, event)
    else:
        await manager.broadcast_all(event)
