from fastapi import APIRouter, Depends, Query, status

from common.auth.security import AdminUser, CurrentUser, get_current_token
from common.exceptions import OasisException
from services.auth_service.logic.manager import AuthManager
from services.auth_service.schemas.auth import (
    AdminUserUpdate,
    PaginatedUsersResponse,
    UserResponse,
    UserUpdate,
)

router = APIRouter()


@router.get("/", response_model=PaginatedUsersResponse)
async def list_users(
    admin: AdminUser,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
):
    """Lista todos los usuarios (solo platform admin)."""
    users, count = await AuthManager.list_all_users(offset, limit, search)
    return {"users": users, "count": count}


@router.patch("/{user_id}/admin", response_model=UserResponse)
async def set_platform_admin(
    user_id: str,
    data: AdminUserUpdate,
    admin: AdminUser,
):
    """Promueve o degrada a un usuario como platform admin."""
    if user_id == str(admin.id):
        raise OasisException(
            code="self_admin_change_forbidden",
            message="No puedes cambiar tu propio status de admin.",
            status_code=400,
        )
    profile = await AuthManager.set_platform_admin(user_id, data.is_platform_admin)
    return profile


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    user: CurrentUser,
    token: str = Depends(get_current_token),
):
    """Retorna datos de la tabla profiles (no auth.users)."""
    profile = await AuthManager.get_my_profile(token, str(user.id))
    return profile


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    data: UserUpdate,
    user: CurrentUser,
    token: str = Depends(get_current_token),
):
    raw = data.model_dump(exclude_unset=True)

    # Separar updates de auth (email/password) vs profile (full_name, avatar_url)
    auth_payload = {}
    if "email" in raw:
        auth_payload["email"] = raw.pop("email")
    if "password" in raw:
        auth_payload["password"] = raw.pop("password")

    # Update auth attributes si hay cambios
    if auth_payload:
        await AuthManager.update_my_user(token, str(user.id), auth_payload)

    # Update profile attributes si hay cambios
    profile_data = {}
    if "full_name" in raw:
        profile_data["full_name"] = raw["full_name"]
    if "avatar_url" in raw:
        profile_data["avatar_url"] = raw["avatar_url"]

    if profile_data:
        profile = await AuthManager.update_my_profile(token, profile_data)
    else:
        # Re-fetch para devolver datos actualizados
        profile = await AuthManager.get_my_profile(token, str(user.id))

    return profile



@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_global(
    user_id: str,
    admin: AdminUser,
):
    if user_id == str(admin.id):
        raise OasisException(
            code="self_delete_forbidden",
            message="No puedes auto-eliminarte.",
            status_code=400,
        )

    await AuthManager.delete_user_by_admin(user_id)
    return None
