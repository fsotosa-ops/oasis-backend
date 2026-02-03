import os
from dotenv import load_dotenv

from supabase import AsyncClient, acreate_client, ClientOptions

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# 1. Cliente Publico (Singleton) — usa anon key
_public_client: AsyncClient | None = None


async def get_public_client() -> AsyncClient:
    global _public_client
    if not _public_client:
        _public_client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)
    return _public_client


# 2. Cliente Admin (Singleton) — usa service-role key
_admin_client: AsyncClient | None = None


async def get_admin_client() -> AsyncClient:
    global _admin_client
    if not _admin_client:
        _admin_client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)
    return _admin_client


# 3. Cliente Scoped (por request) — inyecta JWT del usuario para RLS
async def get_scoped_client(token: str) -> AsyncClient:
    return await acreate_client(
        SUPABASE_URL,
        SUPABASE_ANON_KEY,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )
