import logging
import os

import httpx
from fastapi import APIRouter

from common.auth.security import CurrentUser
from common.exceptions import OasisException

logger = logging.getLogger("oasis.analytics")

router = APIRouter()

SUPERSET_URL = os.getenv("SUPERSET_URL", "")
SUPERSET_ADMIN_USERNAME = os.getenv("SUPERSET_ADMIN_USERNAME", "")
SUPERSET_ADMIN_PASSWORD = os.getenv("SUPERSET_ADMIN_PASSWORD", "")
SUPERSET_DASHBOARD_ID = os.getenv("SUPERSET_DASHBOARD_ID", "")


async def _get_superset_guest_token(user, user_org_id: str | None) -> str:
    """Obtiene un guest token de Superset para embeber dashboards."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Login a Superset para obtener access token
        login_resp = await client.post(
            f"{SUPERSET_URL}/api/v1/security/login",
            json={
                "username": SUPERSET_ADMIN_USERNAME,
                "password": SUPERSET_ADMIN_PASSWORD,
                "provider": "db",
            },
        )
        if login_resp.status_code != 200:
            logger.error("Superset login failed: %s", login_resp.text)
            raise OasisException(
                code="superset_login_failed",
                message="No se pudo autenticar con Superset.",
                status_code=502,
            )
        access_token = login_resp.json()["access_token"]
        auth_header = {"Authorization": f"Bearer {access_token}"}

        # 2. Obtener CSRF token
        csrf_resp = await client.get(
            f"{SUPERSET_URL}/api/v1/security/csrf_token/",
            headers=auth_header,
        )
        if csrf_resp.status_code != 200:
            logger.error("Superset CSRF fetch failed: %s", csrf_resp.text)
            raise OasisException(
                code="superset_csrf_failed",
                message="No se pudo obtener CSRF token de Superset.",
                status_code=502,
            )
        csrf_token = csrf_resp.json()["result"]

        # 3. Construir RLS filters
        rls = []
        is_admin = user.user_metadata.get("is_platform_admin", False)
        if not is_admin and user_org_id:
            rls.append({"clause": f"org_id = '{user_org_id}'"})

        # 4. Crear guest token
        guest_resp = await client.post(
            f"{SUPERSET_URL}/api/v1/security/guest_token/",
            headers={
                **auth_header,
                "X-CSRFToken": csrf_token,
                "Referer": SUPERSET_URL,
            },
            json={
                "resources": [
                    {"type": "dashboard", "id": SUPERSET_DASHBOARD_ID}
                ],
                "rls": rls,
                "user": {
                    "username": user.email or str(user.id),
                    "first_name": user.user_metadata.get("full_name", "User"),
                    "last_name": "",
                },
            },
        )
        if guest_resp.status_code != 200:
            logger.error("Superset guest token failed: %s", guest_resp.text)
            raise OasisException(
                code="superset_guest_token_failed",
                message="No se pudo crear guest token de Superset.",
                status_code=502,
            )
        return guest_resp.json()["token"]


@router.post("/guest-token")
async def get_guest_token(user: CurrentUser):
    """Genera un guest token de Superset para el usuario actual."""
    if not SUPERSET_URL or not SUPERSET_ADMIN_USERNAME:
        raise OasisException(
            code="superset_not_configured",
            message="Superset no esta configurado en el servidor.",
            status_code=503,
        )

    # Determinar org_id del usuario (primera membresía activa)
    user_org_id = None
    # user.user_metadata puede contener org info, pero usamos memberships
    # Para simplificar, pasamos None si es platform admin (ve todo)
    is_admin = user.user_metadata.get("is_platform_admin", False)
    if not is_admin:
        # Intentar obtener org_id de user_metadata si esta disponible
        user_org_id = user.user_metadata.get("organization_id")

    token = await _get_superset_guest_token(user, user_org_id)
    return {"token": token}
