from __future__ import annotations

import logging
import os

from common.events.schemas import RealtimeEvent

logger = logging.getLogger("oasis.events.publisher")

CHANNEL = "platform:events"

_redis = None


def _get_redis():
    """Lazy-init singleton for the async Upstash REST client."""
    global _redis
    if _redis is not None:
        return _redis

    url = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("UPSTASH_REDIS_TOKEN")
    if not url or not token:
        logger.warning("Upstash credentials not set — pub/sub publish disabled")
        return None

    try:
        from upstash_redis.asyncio import Redis

        _redis = Redis(url=url, token=token)
        logger.info("Async publisher ready (Upstash REST → %s)", url)
    except Exception:
        logger.exception("Failed to initialise async Redis publisher")

    return _redis


async def publish_event(event: RealtimeEvent) -> None:
    """Publish a realtime event to Redis — fire-and-forget, never raises.

    Uses Upstash REST API so no persistent TCP connection is required on
    the publisher side. Delivery to native-protocol subscribers is handled
    by Upstash internally.
    """
    r = _get_redis()
    if r is None:
        return
    try:
        await r.publish(CHANNEL, event.model_dump_json())
        logger.debug("Published %s (org=%s)", event.type, event.org_id)
    except Exception:
        logger.exception("publish_event failed — event dropped: %s", event.type)
