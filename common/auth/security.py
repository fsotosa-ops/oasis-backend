from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.database.client import get_public_client, get_scoped_client
from common.exceptions import ForbiddenError, UnauthorizedError

security_scheme = HTTPBearer()


# ---------------------------------------------------------------------------
# Token + current user
# ---------------------------------------------------------------------------
async def get_current_token(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
) -> str:
    """Extrae el token JWT crudo."""
    return creds.credentials


async def get_current_user(token: str = Depends(get_current_token)):
    """Valida el token con Supabase. AuthApiError sube al gateway si falla."""
    client = await get_public_client()
    user_response = await client.auth.get_user(token)

    if not user_response.user:
        raise UnauthorizedError("Sesion invalida o expirada")

    return user_response.user


# ---------------------------------------------------------------------------
# Platform admin guard
# ---------------------------------------------------------------------------
class PlatformAdminRequired:
    async def __call__(self, user=Depends(get_current_user)):
        metadata = getattr(user, "user_metadata", None) or {}
        is_admin = metadata.get("is_platform_admin", False)
        if not is_admin:
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
        metadata = getattr(user, "user_metadata", None) or {}
        if metadata.get("is_platform_admin", False):
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