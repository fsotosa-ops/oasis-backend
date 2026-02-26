import logging
from uuid import UUID

from fastapi import APIRouter, Depends

from common.auth.security import CurrentUser, get_current_user, get_user_memberships
from common.database.client import get_admin_client
from common.exceptions import ForbiddenError, NotFoundError
from services.crm_service.crud import org_profiles as crud
from services.crm_service.dependencies import _check_platform_admin, _find_membership
from services.crm_service.schemas.org_profiles import OrgProfileResponse, OrgProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

WRITE_ROLES = {"owner", "admin"}
READ_ROLES = {"owner", "admin", "facilitador", "participante"}


def _require_org_access(
    org_id: str,
    user: CurrentUser,
    memberships: list[dict],
    *,
    write: bool = False,
) -> None:
    """Verifica que el usuario tiene acceso a esta org (plataform admin ó miembro)."""
    if _check_platform_admin(user, memberships):
        return
    membership = _find_membership(memberships, org_id)
    if not membership:
        raise ForbiddenError("No eres miembro de esta organización")
    role = membership["role"]
    allowed = WRITE_ROLES if write else READ_ROLES
    if role not in allowed:
        raise ForbiddenError(f"Rol '{role}' insuficiente para esta operación")


@router.get("/{org_id}", response_model=OrgProfileResponse)
async def get_org_profile(
    org_id: UUID,
    user=Depends(get_current_user),
    memberships: list[dict] = Depends(get_user_memberships),
):
    """Obtiene el perfil CRM de una organización."""
    _require_org_access(str(org_id), user, memberships, write=False)
    db = await get_admin_client()
    profile = await crud.get_org_profile(db, str(org_id))
    if profile is None:
        # Retornar perfil vacío si aún no existe
        return OrgProfileResponse(org_id=org_id)
    return OrgProfileResponse(**profile)


@router.patch("/{org_id}", response_model=OrgProfileResponse)
async def update_org_profile(
    org_id: UUID,
    body: OrgProfileUpdate,
    user=Depends(get_current_user),
    memberships: list[dict] = Depends(get_user_memberships),
):
    """Crea o actualiza el perfil CRM de una organización (upsert)."""
    _require_org_access(str(org_id), user, memberships, write=True)
    db = await get_admin_client()
    payload = body.model_dump(exclude_none=True)
    updated = await crud.upsert_org_profile(db, str(org_id), payload)
    return OrgProfileResponse(**updated)
