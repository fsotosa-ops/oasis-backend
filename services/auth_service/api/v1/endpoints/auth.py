from fastapi import APIRouter, Depends, Query

from common.auth.security import get_current_token
from services.auth_service.logic.manager import AuthManager
from services.auth_service.schemas.auth import (
    OAuthUrlResponse,
    PasswordResetRequest,
    PasswordUpdate,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

router = APIRouter()


@router.post("/register", status_code=201)
async def register(user: UserRegister):
    session = await AuthManager.register(user)
    if not session:
        return {"message": "Registro exitoso. Revisa tu email para confirmar."}
    return _build_response(session)


@router.post("/login", response_model=TokenResponse)
async def login(creds: UserLogin):
    session = await AuthManager.login(creds.email, creds.password)
    return _build_response(session)


@router.get("/login/oauth", response_model=OAuthUrlResponse)
async def login_oauth(
    provider: str = Query(..., description="google, github..."),
    redirect_to: str = Query(..., description="Frontend callback URL"),
):
    url = await AuthManager.get_oauth_url(provider, redirect_to)
    return {"url": url}


@router.get("/callback", response_model=TokenResponse)
async def oauth_callback(code: str = Query(..., description="Auth code from Supabase redirect")):
    """Intercambia el code de OAuth por access_token + refresh_token."""
    session = await AuthManager.exchange_code_for_session(code)
    return _build_response(session)


@router.post("/password/recovery")
async def request_password_recovery(data: PasswordResetRequest):
    """Envia email de recuperacion de password."""
    await AuthManager.request_password_recovery(data.email)
    return {"message": "Si el email existe, recibiras un enlace de recuperacion."}


@router.post("/password/update")
async def update_password(
    data: PasswordUpdate,
    token: str = Depends(get_current_token),
):
    """Actualiza password usando el token de reset (viene en el header tras el redirect)."""
    await AuthManager.update_password(token, data.new_password)
    return {"message": "Password actualizado exitosamente."}


def _build_response(session) -> dict:
    user = session.user
    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.user_metadata.get("full_name"),
            avatar_url=user.user_metadata.get("avatar_url"),
            is_platform_admin=user.user_metadata.get("is_platform_admin", False),
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    ).model_dump()
