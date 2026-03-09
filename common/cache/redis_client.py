"""Upstash Redis cache layer — HTTP-based, serverless-friendly.

Provides a graceful-degradation singleton: if Redis is unavailable or
UPSTASH_REDIS_URL is not set, every helper silently returns None / does
nothing so the app keeps working without cache.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("oasis.cache")

_redis = None
_initialized = False


def _get_redis():
    """Lazy-init singleton for the Upstash Redis client."""
    global _redis, _initialized
    if _initialized:
        return _redis
    _initialized = True

    url = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("UPSTASH_REDIS_TOKEN")
    if not url or not token:
        logger.warning("UPSTASH_REDIS_URL/TOKEN not set — cache disabled")
        return None

    try:
        from upstash_redis import Redis

        _redis = Redis(url=url, token=token)
        logger.info("Redis cache connected (%s)", url)
    except Exception:
        logger.exception("Failed to initialize Redis client — cache disabled")
        _redis = None

    return _redis


# ---------------------------------------------------------------------------
# Public helpers (all graceful — never raise on Redis failure)
# ---------------------------------------------------------------------------

def cache_get(key: str) -> str | None:
    try:
        r = _get_redis()
        if r is None:
            return None
        return r.get(key)
    except Exception:
        logger.warning("cache_get(%s) failed", key, exc_info=True)
        return None


def cache_set(key: str, value: str, ttl_seconds: int = 300) -> None:
    try:
        r = _get_redis()
        if r is None:
            return
        r.set(key, value, ex=ttl_seconds)
    except Exception:
        logger.warning("cache_set(%s) failed", key, exc_info=True)


def cache_delete(key: str) -> None:
    try:
        r = _get_redis()
        if r is None:
            return
        r.delete(key)
    except Exception:
        logger.warning("cache_delete(%s) failed", key, exc_info=True)


def cache_get_json(key: str) -> dict | list | None:
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def cache_set_json(key: str, value, ttl_seconds: int = 300) -> None:
    try:
        cache_set(key, json.dumps(value, default=str), ttl_seconds)
    except (TypeError, ValueError):
        logger.warning("cache_set_json(%s) serialization failed", key, exc_info=True)


def cache_ping() -> bool:
    """Health-check helper. Returns True if Redis responds."""
    try:
        r = _get_redis()
        if r is None:
            return False
        r.ping()
        return True
    except Exception:
        return False
