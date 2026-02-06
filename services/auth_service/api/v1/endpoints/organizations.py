from fastapi import APIRouter, Depends, status

from common.auth.security import (
    AdminUser,
    CurrentUser,
    OrgContext,
    OrgRoleRequired,
    get_current_token,
)
from services.auth_service.logic.org_manager import OrgManager
from services.auth_service.schemas.auth import (
    MemberInvite,
    MemberResponse,
    MemberUpdate,
    OrgCreate,
    OrgResponse,
    OrgUpdate,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


@router.get("")
async def list_organizations(
    user: CurrentUser,
    token: str = Depends(get_current_token),
):
    """Lista organizaciones. Platform admin ve TODAS, usuarios normales solo las suyas."""
    if user.user_metadata.get("is_platform_admin", False):
        return await OrgManager.list_all_orgs()
    return await OrgManager.list_my_orgs(token, str(user.id))


@router.get("/{org_id}", response_model=OrgResponse)
async def get_organization(
    org_id: str,
    user: CurrentUser,
    token: str = Depends(get_current_token),
):
    """Obtiene detalle de una organizacion."""
    return await OrgManager.get_org(token, org_id)


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrgCreate,
    user: AdminUser,
):
    """Crea una organizacion (solo platform admin). El owner_user_id indica quien sera el owner."""
    payload = data.model_dump(exclude_unset=True, exclude={"owner_user_id"})
    owner_id = data.owner_user_id or str(user.id)
    return await OrgManager.create_org(payload, owner_id)


@router.patch("/{org_id}", response_model=OrgResponse)
async def update_organization(
    data: OrgUpdate,
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Actualiza una organizacion (requiere owner o admin)."""
    payload = data.model_dump(exclude_unset=True)
    return await OrgManager.update_org(token, org.organization_id, payload)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner")),
):
    """Elimina una organizacion (solo owner)."""
    await OrgManager.delete_org(token, org.organization_id)
    return None


# ---------------------------------------------------------------------------
# Members management
# ---------------------------------------------------------------------------


@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: str,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin", "facilitador", "participante")),
):
    """Lista los miembros de una organizacion."""
    return await OrgManager.list_members(token, org_id)


@router.post(
    "/{org_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    data: MemberInvite,
    user: CurrentUser,
    token: str = Depends(get_current_token),
    org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Invita un usuario a la organizacion (requiere owner o admin)."""
    return await OrgManager.invite_member(
        token, org.organization_id, data.user_id, data.role, str(user.id)
    )


@router.patch("/{org_id}/members/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: str,
    data: MemberUpdate,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Actualiza rol o status de un miembro (requiere owner o admin)."""
    payload = data.model_dump(exclude_unset=True)
    return await OrgManager.update_member(token, member_id, payload)


@router.delete(
    "/{org_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    member_id: str,
    token: str = Depends(get_current_token),
    _org: OrgContext = Depends(OrgRoleRequired("owner", "admin")),
):
    """Elimina un miembro de la organizacion (requiere owner o admin)."""
    await OrgManager.remove_member(token, member_id)
    return None
