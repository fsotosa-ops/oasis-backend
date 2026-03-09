from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.cache.redis_client import cache_get, cache_set
from common.database.client import get_admin_client, get_scoped_client
from common.exceptions import ForbiddenError, UnauthorizedError

logger = logging.getLogger("oasis.auth")

security_scheme = HTTPBearer()

# ---------------------------------------------------------------------------
# JWKS-based local JWT validation (eliminates GoTrue HTTP on every request)
# ---------------------------------------------------------------------------
_jwks_keys: dict | None = None
_jwks_fetched_at: float = 0
_JWKS_REFRESH_INTERVAL = 3600  # 1 hour


def _fetch_jwks() -> dict:
    """Fetch JWKS from Supabase GoTrue (synchronous HTTP — called rarely)."""
    import httpx

    jwks_url = os.getenv("SUPABASE_JWKS_URL")
    if not jwks_url:
        # Derive from SUPABASE_URL if JWKS URL not set explicitly
        supabase_url = os.getenv("SUPABASE_URL", "")
        jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"

    resp = httpx.get(jwks_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_jwks() -> dict:
    """Return cached JWKS, refreshing if stale (> 1h)."""
    global _jwks_keys, _jwks_fetched_at

    now = time.time()
    if _jwks_keys and (now - _jwks_fetched_at) < _JWKS_REFRESH_INTERVAL:
        return _jwks_keys

    try:
        _jwks_keys = _fetch_jwks()
        _jwks_fetched_at = now
        logger.info("JWKS refreshed successfully")
    except Exception:
        if _jwks_keys:
            logger.warning("JWKS refresh failed — using stale keys", exc_info=True)
        else:
            logger.error("JWKS fetch failed and no cached keys available", exc_info=True)
            raise

    return _jwks_keys


class _JWTUser:
    """Lightweight user object extracted from JWT claims, compatible with
    the Supabase user object interface used throughout the codebase."""

    def __init__(self, claims: dict):
        self.id = claims.get("sub")
        self.email = claims.get("email")
        self.user_metadata = claims.get("user_metadata", {})
        self.app_metadata = claims.get("app_metadata", {})
        self.role = claims.get("role")
        self._claims = claims


def _decode_jwt_local(token: str) -> _JWTUser:
    """Validate and decode a Supabase JWT locally using JWKS.

    Verifies signature, expiration, and issuer.
    """
    from jose import JWTError, jwt

    jwks = _get_jwks()
    supabase_url = os.getenv("SUPABASE_URL", "")
    expected_issuer = f"{supabase_url}/auth/v1"

    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=expected_issuer,
            options={
                "verify_aud": False,  # Supabase tokens don't always set aud
                "verify_exp": True,
                "verify_iss": True,
            },
        )
        return _JWTUser(payload)
    except JWTError:
        raise


# ---------------------------------------------------------------------------
# Token + current user
# ---------------------------------------------------------------------------
async def get_current_token(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
) -> str:
    """Extrae el token JWT crudo."""
    return creds.credentials


async def get_current_user(token: str = Depends(get_current_token)):
    """Validate JWT locally via JWKS. Falls back to GoTrue on failure."""
    try:
        return _decode_jwt_local(token)
    except Exception:
        logger.debug("Local JWT validation failed — falling back to GoTrue")

    # Fallback: validate via GoTrue HTTP (original behavior)
    from common.database.client import get_public_client

    client = await get_public_client()
    user_response = await client.auth.get_user(token)

    if not user_response.user:
        raise UnauthorizedError("Sesion invalida o expirada")

    return user_response.user


# ---------------------------------------------------------------------------
# Platform admin helper (Redis cache + DB fallback)
# ---------------------------------------------------------------------------
async def is_platform_admin(user) -> bool:
    """Checks is_platform_admin with Redis cache (TTL 5min), then DB fallback."""
    user_id = str(user.id)

    # 1. Check Redis cache
    cached = cache_get(f"admin:{user_id}")
    if cached is not None:
        return cached == "true"

    # 2. JWT fast-path
    metadata = getattr(user, "user_metadata", None) or {}
    if metadata.get("is_platform_admin", False):
        cache_set(f"admin:{user_id}", "true", ttl_seconds=300)
        return True

    # 3. DB fallback (JWT might be stale)
    admin = await get_admin_client()
    response = (
        await admin.table("profiles")
        .select("is_platform_admin")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    result = bool(response.data.get("is_platform_admin", False)) if response.data else False
    cache_set(f"admin:{user_id}", "true" if result else "false", ttl_seconds=300)
    return result


# ---------------------------------------------------------------------------
# Platform admin guard
# ---------------------------------------------------------------------------
class PlatformAdminRequired:
    async def __call__(self, user=Depends(get_current_user)):
        if not await is_platform_admin(user):
            raise ForbiddenError(
                message="Acceso denegado: Se requieren permisos de Administrador."
            )
        return user


# ---------------------------------------------------------------------------
# Organization membership helpers
# ---------------------------------------------------------------------------
async def get_user_memberships(
    token: str = Depends(get_current_token),
    user=Depends(get_current_user),
) -> list[dict]:
    """Consulta organization_members con join a organizations para el usuario actual."""
    client = await get_scoped_client(token)
    response = (
        await client.table("organization_members")
        .select("id, organization_id, role, status, joined_at, organizations(id, name, slug, type)")
        .eq("user_id", str(user.id))
        .execute()
    )
    return response.data or []


@dataclass
class OrgContext:
    organization_id: str
    role: str
    status: str


class OrgRoleRequired:
    """Factory de dependency que valida el rol del usuario en una org (usa path param org_id).
    Los platform admins pueden acceder a cualquier organizacion sin ser miembros."""

    def __init__(self, *allowed_roles: str):
        self.allowed_roles = set(allowed_roles)

    async def __call__(
        self,
        org_id: str = Path(...),
        user=Depends(get_current_user),
        memberships: list[dict] = Depends(get_user_memberships),
    ) -> OrgContext:
        # Platform admins tienen acceso total a cualquier organizacion
        if await is_platform_admin(user):
            return OrgContext(
                organization_id=org_id,
                role="owner",
                status="active",
            )

        for m in memberships:
            if m["organization_id"] == org_id:
                if m["status"] != "active":
                    raise ForbiddenError("Membresia no activa en esta organizacion")
                if m["role"] not in self.allowed_roles:
                    raise ForbiddenError(
                        f"Rol '{m['role']}' insuficiente. Se requiere: {', '.join(self.allowed_roles)}"
                    )
                return OrgContext(
                    organization_id=org_id,
                    role=m["role"],
                    status=m["status"],
                )
        raise ForbiddenError("No eres miembro de esta organizacion")


# ---------------------------------------------------------------------------
# Type aliases for dependency injection
# ---------------------------------------------------------------------------
CurrentUser = Annotated[object, Depends(get_current_user)]
AdminUser = Annotated[object, Depends(PlatformAdminRequired())]
UserMemberships = Annotated[list[dict], Depends(get_user_memberships)]
