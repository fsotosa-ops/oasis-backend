from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Query

from common.auth.security import get_current_user, get_user_memberships
from common.exceptions import ForbiddenError

FUNDACION_SUMMER_NAME = "Fundación Summer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _check_platform_admin(user, memberships: list[dict]) -> bool:
    """Replica crm.is_platform_admin(): metadata flag OR admin/owner de Fundación Summer."""
    if user.user_metadata.get("is_platform_admin", False):
        return True
    for m in memberships:
        org = m.get("organizations") or {}
        if (
            org.get("name") == FUNDACION_SUMMER_NAME
            and m.get("role") in ("owner", "admin")
            and m.get("status") == "active"
        ):
            return True
    return False


def _find_membership(memberships: list[dict], org_id: str) -> Optional[dict]:
    """Busca membresía activa del usuario en la org dada."""
    for m in memberships:
        if m["organization_id"] == org_id and m["status"] == "active":
            return m
    return None


# ---------------------------------------------------------------------------
# CrmContext — resultado de la autorización
# ---------------------------------------------------------------------------
@dataclass
class CrmContext:
    user_id: str
    organization_id: Optional[str]
    is_platform_admin: bool
    role: Optional[str]  # role dentro de la org (o "owner" virtual para platform admins)


# ---------------------------------------------------------------------------
# CrmOrgAccess — dependency class configurable
# ---------------------------------------------------------------------------
class CrmOrgAccess:
    """Dependency que valida membresía/roles del usuario para el CRM.

    - org_required=True  → organization_id Query es obligatorio (notes, tasks, stats).
    - org_required=False → organization_id es opcional; platform admins ven todo sin org.
    - allowed_roles      → roles permitidos dentro de la org.
    - write              → si True, requiere admin/owner (no facilitador).
    """

    def __init__(
        self,
        *allowed_roles: str,
        org_required: bool = True,
        write: bool = False,
    ):
        self.allowed_roles = set(allowed_roles) if allowed_roles else {"facilitador", "admin", "owner"}
        self.org_required = org_required
        if write:
            self.allowed_roles = {"admin", "owner"}

    async def __call__(
        self,
        organization_id: Optional[str] = Query(None),
        user=Depends(get_current_user),  # noqa: B008
        memberships: list[dict] = Depends(get_user_memberships),  # noqa: B008
    ) -> CrmContext:
        is_pa = _check_platform_admin(user, memberships)
        user_id = str(user.id)

        # Si org es requerida y no se proporcionó
        if self.org_required and not organization_id:
            if is_pa:
                raise ForbiddenError("organization_id es requerido para este endpoint")
            raise ForbiddenError("organization_id es requerido")

        # Platform admin sin org → acceso global
        if is_pa and not organization_id:
            return CrmContext(
                user_id=user_id,
                organization_id=None,
                is_platform_admin=True,
                role="owner",
            )

        # Platform admin con org → acceso directo
        if is_pa and organization_id:
            return CrmContext(
                user_id=user_id,
                organization_id=organization_id,
                is_platform_admin=True,
                role="owner",
            )

        # Usuario normal → debe tener membresía activa en la org
        if not organization_id:
            raise ForbiddenError("organization_id es requerido")

        membership = _find_membership(memberships, organization_id)
        if not membership:
            raise ForbiddenError("No eres miembro de esta organización")

        role = membership["role"]
        if role not in self.allowed_roles:
            raise ForbiddenError(
                f"Rol '{role}' insuficiente. Se requiere: {', '.join(sorted(self.allowed_roles))}"
            )

        return CrmContext(
            user_id=user_id,
            organization_id=organization_id,
            is_platform_admin=False,
            role=role,
        )


# ---------------------------------------------------------------------------
# Pre-built instances
# ---------------------------------------------------------------------------
# Read access: facilitador, admin, owner — org requerida
CrmReadAccess = CrmOrgAccess("facilitador", "admin", "owner", org_required=True)

# Write access: admin, owner — org requerida
CrmWriteAccess = CrmOrgAccess("admin", "owner", org_required=True)

# Global read: facilitador, admin, owner — org opcional (platform admins ven todo)
CrmGlobalReadAccess = CrmOrgAccess("facilitador", "admin", "owner", org_required=False)

# Global write: admin, owner — org opcional (platform admins editan cualquier contacto sin org)
CrmGlobalWriteAccess = CrmOrgAccess("admin", "owner", org_required=False, write=True)