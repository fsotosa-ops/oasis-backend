import logging

from common.database.client import get_admin_client, get_scoped_client
from common.exceptions import NotFoundError

logger = logging.getLogger("oasis.org_manager")


class OrgManager:

    # ------------------------------------------------------------------
    # Organizations CRUD
    # ------------------------------------------------------------------
    @staticmethod
    async def list_my_orgs(token: str, user_id: str) -> list[dict]:
        """Lista las organizaciones del usuario actual."""
        client = await get_scoped_client(token)
        response = (
            await client.table("organization_members")
            .select(
                "id, organization_id, role, status, joined_at, "
                "organizations(id, name, slug, description, logo_url, type, created_at, updated_at)"
            )
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        # Flatten: extract nested organization data so the response
        # matches the same shape as list_all_orgs() (ApiOrganization[]).
        result = []
        for row in (response.data or []):
            org_data = row.get("organizations")
            if org_data:
                result.append(org_data)
        return result

    @staticmethod
    async def list_all_orgs() -> list[dict]:
        """Lista TODAS las organizaciones (solo para platform admin). Usa admin client para bypassear RLS."""
        admin = await get_admin_client()
        response = (
            await admin.table("organizations")
            .select("id, name, slug, description, logo_url, type, settings, created_at, updated_at")
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    @staticmethod
    async def get_org(token: str, org_id: str) -> dict:
        """Obtiene una organizacion por ID (RLS aplica)."""
        client = await get_scoped_client(token)
        response = (
            await client.table("organizations")
            .select("id, name, slug, description, logo_url, type, settings, created_at, updated_at")
            .eq("id", org_id)
            .single()
            .execute()
        )
        return response.data

    @staticmethod
    async def create_org(data: dict, owner_user_id: str) -> dict:
        """Crea una organizacion y asigna al owner. Usa admin client para bypassear RLS."""
        admin = await get_admin_client()

        # Insertar organizacion
        org_response = (
            await admin.table("organizations")
            .insert(data)
            .execute()
        )
        org = org_response.data[0]

        # Insertar al owner
        await (
            admin.table("organization_members")
            .insert({
                "organization_id": org["id"],
                "user_id": owner_user_id,
                "role": "owner",
                "status": "active",
            })
            .execute()
        )

        return org

    @staticmethod
    async def update_org(token: str, org_id: str, data: dict) -> dict:
        """Actualiza una organizacion (requiere permisos via OrgRoleRequired)."""
        client = await get_scoped_client(token)
        response = (
            await client.table("organizations")
            .update(data)
            .eq("id", org_id)
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def delete_org(token: str, org_id: str) -> None:
        """Elimina una organizacion (cascade elimina members)."""
        client = await get_scoped_client(token)
        await (
            client.table("organizations")
            .delete()
            .eq("id", org_id)
            .execute()
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def resolve_email_to_user_id(email: str) -> str | None:
        """Busca un usuario en profiles por email y devuelve su id o None."""
        admin = await get_admin_client()
        response = (
            await admin.table("profiles")
            .select("id")
            .eq("email", email)
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]["id"]
        return None

    # ------------------------------------------------------------------
    # Members management
    # ------------------------------------------------------------------
    @staticmethod
    async def list_members(token: str, org_id: str) -> list[dict]:
        """Lista los miembros de una organizacion con datos del perfil.
        Usa admin client para bypassear RLS en profiles."""
        admin = await get_admin_client()
        response = (
            await admin.table("organization_members")
            .select(
                "id, organization_id, user_id, role, status, "
                "invited_by, invited_at, joined_at, "
                "profiles!fk_org_members_user_profile(id, email, full_name, is_platform_admin)"
            )
            .eq("organization_id", org_id)
            .execute()
        )
        # Flatten nested profiles data into a 'user' key for the frontend
        result = []
        for row in (response.data or []):
            profile = row.pop("profiles", None)
            if profile:
                row["user"] = profile
            result.append(row)
        return result

    @staticmethod
    async def invite_member(
        token: str, org_id: str, email: str, role: str, invited_by: str
    ) -> dict:
        """Invita un miembro a la organizacion por email (status: invited)."""
        user_id = await OrgManager.resolve_email_to_user_id(email)
        if not user_id:
            raise NotFoundError(f"Usuario con email {email}")
        client = await get_scoped_client(token)
        response = (
            await client.table("organization_members")
            .insert({
                "organization_id": org_id,
                "user_id": user_id,
                "role": role,
                "status": "invited",
                "invited_by": invited_by,
                "invited_at": "now()",
            })
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def update_member(token: str, member_id: str, data: dict) -> dict:
        """Actualiza rol o status de un miembro."""
        client = await get_scoped_client(token)
        response = (
            await client.table("organization_members")
            .update(data)
            .eq("id", member_id)
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def remove_member(token: str, member_id: str) -> None:
        """Elimina un miembro de la organizacion."""
        client = await get_scoped_client(token)
        await (
            client.table("organization_members")
            .delete()
            .eq("id", member_id)
            .execute()
        )

    @staticmethod
    async def add_member(
        token: str, org_id: str, email: str, role: str, added_by: str
    ) -> dict:
        """Agrega un miembro directamente con status active."""
        user_id = await OrgManager.resolve_email_to_user_id(email)
        if not user_id:
            raise NotFoundError(f"Usuario con email {email}")
        client = await get_scoped_client(token)
        response = (
            await client.table("organization_members")
            .insert({
                "organization_id": org_id,
                "user_id": user_id,
                "role": role,
                "status": "active",
                "invited_by": added_by,
                "joined_at": "now()",
            })
            .execute()
        )
        return response.data[0]

    @staticmethod
    async def bulk_add_members(
        token: str, org_id: str, members: list[dict], added_by: str
    ) -> list[dict]:
        """Agrega multiples miembros. Retorna resultados individuales."""
        from postgrest.exceptions import APIError as PostgRESTAPIError

        client = await get_scoped_client(token)
        results = []
        for item in members:
            email = item["email"]
            role = item.get("role", "participante")
            try:
                user_id = await OrgManager.resolve_email_to_user_id(email)
                if not user_id:
                    results.append({"email": email, "success": False, "error": "user_not_found", "member": None})
                    continue
                response = (
                    await client.table("organization_members")
                    .insert({
                        "organization_id": org_id,
                        "user_id": user_id,
                        "role": role,
                        "status": "active",
                        "invited_by": added_by,
                        "joined_at": "now()",
                    })
                    .execute()
                )
                results.append({"email": email, "success": True, "error": None, "member": response.data[0]})
            except PostgRESTAPIError as exc:
                pg_code = getattr(exc, "code", "")
                if pg_code == "23505":
                    results.append({"email": email, "success": False, "error": "already_member", "member": None})
                else:
                    results.append({"email": email, "success": False, "error": str(exc), "member": None})
            except Exception as exc:
                logger.warning("Error adding member %s: %s", email, exc)
                results.append({"email": email, "success": False, "error": str(exc), "member": None})
        return results
