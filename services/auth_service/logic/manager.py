import logging
from typing import Optional

from common.database.client import get_admin_client, get_public_client, get_scoped_client

logger = logging.getLogger("oasis.auth_manager")


class AuthManager:

    @staticmethod
    async def register(data):
        client = await get_public_client()
        res = await client.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {
                "data": {
                    "full_name": data.full_name,
                    "avatar_url": data.avatar_url,
                }
            },
        })
        # Si hay session (email confirmation deshabilitada), registrar en audit
        if res.session:
            try:
                scoped = await get_scoped_client(res.session.access_token)
                await scoped.rpc("log_register", {"p_provider": "email"}).execute()
            except Exception:
                logger.warning("No se pudo registrar log_register RPC", exc_info=True)
        return res.session

    @staticmethod
    async def login(email: str, password: str):
        client = await get_public_client()
        res = await client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        # Registrar login en audit
        if res.session:
            try:
                scoped = await get_scoped_client(res.session.access_token)
                await scoped.rpc("log_login", {"p_provider": "email"}).execute()
            except Exception:
                logger.warning("No se pudo registrar log_login RPC", exc_info=True)
        return res.session

    @staticmethod
    async def get_oauth_url(provider: str, redirect_to: str):
        client = await get_public_client()
        res = await client.auth.sign_in_with_oauth({
            "provider": provider,
            "options": {"redirect_to": redirect_to},
        })
        return res.url

    @staticmethod
    async def exchange_code_for_session(code: str):
        """Intercambia un auth code (OAuth callback) por una sesión."""
        client = await get_public_client()
        res = await client.auth.exchange_code_for_session({"auth_code": code})
        return res.session

    @staticmethod
    async def refresh_session(refresh_token: str):
        """Intercambia un refresh_token por una nueva sesión."""
        client = await get_public_client()
        res = await client.auth.refresh_session(refresh_token)
        return res.session

    @staticmethod
    async def logout(token: str):
        """Revoca la sesión del usuario."""
        client = await get_scoped_client(token)
        await client.auth.sign_out()

    @staticmethod
    async def get_user_memberships(token: str, user_id: str) -> list[dict]:
        """Obtiene las membresías de organizaciones del usuario."""
        client = await get_scoped_client(token)
        response = (
            await client.table("organization_members")
            .select(
                "id, organization_id, role, status, joined_at, "
                "organizations(name, slug)"
            )
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        memberships = []
        for row in (response.data or []):
            org = row.get("organizations") or {}
            memberships.append({
                "id": row["id"],
                "organization_id": row["organization_id"],
                "role": row["role"],
                "status": row["status"],
                "joined_at": row.get("joined_at"),
                "organization_name": org.get("name"),
                "organization_slug": org.get("slug"),
            })
        return memberships

    @staticmethod
    async def get_my_profile(token: str, user_id: str) -> dict:
        """Consulta la tabla profiles via scoped client (respeta RLS)."""
        client = await get_scoped_client(token)
        response = (
            await client.table("profiles")
            .select("id, email, full_name, avatar_url, is_platform_admin, status, created_at, updated_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
        profile = response.data
        profile["organizations"] = await AuthManager.get_user_memberships(token, user_id)
        return profile

    @staticmethod
    async def update_my_profile(token: str, data: dict) -> dict:
        """Update en tabla profiles via scoped client (respeta RLS)."""
        client = await get_scoped_client(token)
        # El RLS de profiles asegura que solo se actualice el propio perfil
        user_resp = await client.auth.get_user(token)
        user_id = str(user_resp.user.id)
        await (
            client.table("profiles")
            .update(data)
            .eq("id", user_id)
            .execute()
        )
        # Re-fetch para devolver datos actualizados
        return await AuthManager.get_my_profile(token, user_id)

    @staticmethod
    async def request_password_recovery(email: str):
        """Envia email de recuperacion de password via Supabase Auth."""
        client = await get_public_client()
        await client.auth.reset_password_email(email)

    @staticmethod
    async def update_password(token: str, new_password: str):
        """Actualiza password usando el token de recovery."""
        # Validar el token para obtener el user_id
        client = await get_public_client()
        user_response = await client.auth.get_user(token)
        user_id = str(user_response.user.id)

        # Actualizar password via admin client
        admin = await get_admin_client()
        res = await admin.auth.admin.update_user_by_id(
            user_id,
            {"password": new_password},
        )
        return res.user

    @staticmethod
    async def update_my_user(token: str, user_id: str, attributes: dict):
        """Actualiza atributos auth del usuario via admin client."""
        admin = await get_admin_client()
        res = await admin.auth.admin.update_user_by_id(user_id, attributes)
        return res.user

    @staticmethod
    async def list_all_users(
        offset: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """Lista todos los usuarios via admin client (bypassa RLS)."""
        admin = await get_admin_client()
        query = admin.table("profiles").select(
            "id, email, full_name, avatar_url, is_platform_admin, status, created_at, updated_at",
            count="exact",
        )
        if search:
            pattern = f"%{search}%"
            query = query.or_(f"email.ilike.{pattern},full_name.ilike.{pattern}")
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        response = await query.execute()
        return response.data, response.count

    @staticmethod
    async def set_platform_admin(user_id: str, is_admin: bool) -> dict:
        """Actualiza is_platform_admin en profiles y en auth.users metadata."""
        admin = await get_admin_client()

        # 1. Actualizar tabla profiles
        await (
            admin.table("profiles")
            .update({"is_platform_admin": is_admin})
            .eq("id", user_id)
            .execute()
        )

        # 2. Sincronizar raw_user_meta_data en auth.users
        await admin.auth.admin.update_user_by_id(
            user_id,
            {"user_metadata": {"is_platform_admin": is_admin}},
        )

        # 3. Re-fetch para devolver el perfil actualizado
        profile_resp = (
            await admin.table("profiles")
            .select("id, email, full_name, avatar_url, is_platform_admin, status, created_at, updated_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return profile_resp.data

    @staticmethod
    async def update_user_by_admin(user_id: str, data: dict) -> dict:
        """Actualiza perfil de un usuario via admin client (bypassa RLS)."""
        admin = await get_admin_client()

        profile_fields = {}
        if "full_name" in data:
            profile_fields["full_name"] = data["full_name"]
        if "status" in data:
            profile_fields["status"] = data["status"]
        if "is_platform_admin" in data:
            profile_fields["is_platform_admin"] = data["is_platform_admin"]

        # 1. Actualizar tabla profiles
        if profile_fields:
            await (
                admin.table("profiles")
                .update(profile_fields)
                .eq("id", user_id)
                .execute()
            )

        # 2. Si is_platform_admin cambia, sincronizar con auth.users metadata
        if "is_platform_admin" in data:
            await admin.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": {"is_platform_admin": data["is_platform_admin"]}},
            )

        # 3. Re-fetch para devolver el perfil actualizado
        profile_resp = (
            await admin.table("profiles")
            .select("id, email, full_name, avatar_url, is_platform_admin, status, created_at, updated_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return profile_resp.data

    @staticmethod
    async def delete_user_by_admin(target_user_id: str):
        admin = await get_admin_client()
        await admin.auth.admin.delete_user(target_user_id)
        return True
