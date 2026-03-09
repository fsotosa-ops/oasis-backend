import asyncio
import logging

from fastapi import APIRouter, Depends, Query

from common.auth.security import get_current_token, get_current_user
from common.database.client import get_admin_client
from services.auth_service.logic.manager import AuthManager
from services.auth_service.schemas.auth import (
    OAuthUrlResponse,
    PasswordResetRequest,
    PasswordUpdate,
    RefreshTokenRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

logger = logging.getLogger("oasis.auth")

router = APIRouter()


@router.post("/register", status_code=201)
async def register(user: UserRegister):
    session = await AuthManager.register(user)
    if not session:
        return {"message": "Registro exitoso. Revisa tu email para confirmar."}
    response = await _build_response(session)
    await _log_auth_event("REGISTER", str(session.user.id), session.user.email, {"provider": "email"})
    return response


@router.post("/login", response_model=TokenResponse)
async def login(creds: UserLogin):
    session = await AuthManager.login(creds.email, creds.password)
    response = await _build_response(session)
    await _log_auth_event("LOGIN", str(session.user.id), session.user.email, {"provider": "email"})
    return response


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
    response = await _build_response(session)
    provider = session.user.app_metadata.get("provider", "oauth")
    await _log_auth_event("LOGIN", str(session.user.id), session.user.email, {"provider": provider})
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshTokenRequest):
    """Intercambia un refresh_token por un nuevo par de tokens."""
    session = await AuthManager.refresh_session(data.refresh_token)
    return await _build_response(session)


@router.post("/logout", status_code=204)
async def logout(
    token: str = Depends(get_current_token),
    user=Depends(get_current_user),
):
    """Revoca la sesión actual del usuario."""
    await _log_auth_event("LOGOUT", str(user.id), user.email)
    await AuthManager.logout(token)


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


async def _build_response(session) -> dict:
    user = session.user
    admin = await get_admin_client()

    memberships, profile_resp = await _gather(
        AuthManager.get_user_memberships(session.access_token, str(user.id)),
        # Use limit(1) instead of maybe_single() — avoids db_204 error when no row found
        admin.table("profiles").select("is_platform_admin").eq("id", str(user.id)).limit(1).execute(),
    )

    # Read is_platform_admin from DB (source of truth — JWT may be stale
    # if promotion was done via SQL without going through the API)
    is_admin = False
    profile_data = (profile_resp.data or [None])[0] if profile_resp else None
    if profile_data:
        is_admin = bool(profile_data.get("is_platform_admin", False))
    else:
        is_admin = user.user_metadata.get("is_platform_admin", False)

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.user_metadata.get("full_name"),
            avatar_url=user.user_metadata.get("avatar_url"),
            is_platform_admin=is_admin,
            created_at=user.created_at,
            updated_at=user.updated_at,
            organizations=memberships,
        ),
    ).model_dump()


async def _gather(*coros):
    """Run coroutines concurrently, return results in order."""
    return await asyncio.gather(*coros)


async def _log_auth_event(action: str, user_id: str, email: str, metadata: dict | None = None) -> None:
    """Fire-and-forget: insert an auth event into audit.logs via admin client."""
    try:
        admin = await get_admin_client()
        await (
            admin.schema("audit")
            .table("logs")
            .insert({
                "actor_id": user_id,
                "actor_email": email,
                "category_code": "auth",
                "action": action,
                "resource": "session",
                "resource_id": user_id,
                "metadata": metadata or {},
            })
            .select("id")
            .execute()
        )
    except Exception as exc:
        logger.warning("Audit log failed for %s (%s): %s", action, email, exc)
