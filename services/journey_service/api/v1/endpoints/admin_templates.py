"""
Template endpoints para crear journeys pre-configurados out-of-the-box.
Actualmente soporta:
  POST /{org_id}/admin/journeys/templates/onboarding  — crea el Journey de Onboarding de Perfil CRM
"""
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from common.auth.security import OrgRoleRequired
from common.database.client import get_admin_client
from fastapi import Depends
from services.gamification_service.crud import config as gamif_config_crud
from services.journey_service.crud import journeys as journeys_crud
from services.journey_service.crud import steps as steps_crud
from services.journey_service.schemas.journeys import (
    GamificationRules,
    JourneyAdminRead,
    JourneyCreate,
    StepCreate,
)
from supabase import AsyncClient

router = APIRouter()

AdminRequired = OrgRoleRequired("owner", "admin")

# ---------------------------------------------------------------------------
# Template definition: 4 steps agrupados para el Journey de Onboarding
# ---------------------------------------------------------------------------
_ONBOARDING_STEPS = [
    {
        "title": "Tu trayectoria",
        "field_names": ["occupation", "education_level"],
        "description": "Cuéntanos un poco sobre tu camino profesional y académico.",
        "icon": "🎓",
        "points": 25,
    },
    {
        "title": "¿De dónde eres?",
        "field_names": ["country", "state", "city"],
        "description": "Tu ubicación nos ayuda a conectarte con la comunidad más cercana.",
        "icon": "🌍",
        "points": 25,
    },
    {
        "title": "Datos personales",
        "field_names": ["birth_date", "gender"],
        "description": "Un poco más sobre ti para personalizar tu experiencia.",
        "icon": "👤",
        "points": 25,
    },
    {
        "title": "Contacto y empresa",
        "field_names": ["phone", "company"],
        "description": "¿Cómo podemos contactarte y dónde trabajas?",
        "icon": "📬",
        "points": 25,
    },
]


class OnboardingTemplateResponse(BaseModel):
    journey: JourneyAdminRead
    already_existed: bool


@router.post(
    "/{org_id}/admin/journeys/templates/onboarding",
    response_model=OnboardingTemplateResponse,
    status_code=200,
    summary="Crear Journey de Onboarding de Perfil CRM",
    description=(
        "Crea el journey pre-configurado de onboarding (4 steps de tipo profile_field) "
        "y lo asocia en gamification_config.profile_completion_journey_id. "
        "Si ya existe un journey configurado, retorna already_existed=true sin modificar nada."
    ),
)
async def create_onboarding_template(
    org_id: str,
    _ctx=Depends(AdminRequired),  # noqa: B008
    db: AsyncClient = Depends(get_admin_client),  # noqa: B008
) -> dict:
    org_uuid = UUID(org_id)

    # 1. Verificar si ya existe journey configurado
    config = await gamif_config_crud.get_config(db, org_uuid)
    existing_journey_id = (config or {}).get("profile_completion_journey_id")

    if existing_journey_id:
        # Ya existe — devolver el journey existente
        existing = await journeys_crud.get_journey_admin(db, UUID(existing_journey_id))
        if existing:
            return {
                "journey": existing,
                "already_existed": True,
            }

    # 2. Crear el journey
    slug = f"onboarding-perfil-{org_id[:8]}"
    journey_create = JourneyCreate(
        title="Journey de Bienvenida",
        slug=slug,
        description="Completa tu perfil y gana puntos mientras nos conocemos mejor.",
        is_active=True,
        metadata={"is_onboarding": True},
    )
    journey = await journeys_crud.create_journey(db, org_id, journey_create)
    journey_id = UUID(journey["id"])

    # 3. Crear los steps de tipo profile_field
    for i, step_def in enumerate(_ONBOARDING_STEPS):
        step_create = StepCreate(
            title=step_def["title"],
            type="profile_field",
            order_index=i,
            config={
                "field_names": step_def["field_names"],
                "description": step_def["description"],
                "icon": step_def["icon"],
            },
            gamification_rules=GamificationRules(base_points=step_def["points"]),
        )
        await steps_crud.create_step(db, journey_id, step_create)

    # 4. Actualizar gamification_config con el nuevo journey_id
    gamif_upsert_data = {
        "organization_id": org_id,
        "profile_completion_journey_id": str(journey_id),
    }
    existing_config = config or {}
    # Preservar campos existentes (profile_completion_step_id, level_thresholds, etc.)
    merged = {**existing_config, **gamif_upsert_data}
    # Limpiar campos que no son columnas reales (ej: id, created_at, updated_at)
    for key in ["id", "created_at", "updated_at"]:
        merged.pop(key, None)

    await db.schema("journeys").table("gamification_config").upsert(
        merged, on_conflict="organization_id"
    ).execute()

    # 5. Obtener el journey completo con stats
    full_journey = await journeys_crud.get_journey_admin(db, journey_id)
    # Agregar stats vacías si no están (journey recién creado)
    if full_journey:
        full_journey.setdefault("total_steps", len(_ONBOARDING_STEPS))
        full_journey.setdefault("total_enrollments", 0)
        full_journey.setdefault("active_enrollments", 0)
        full_journey.setdefault("completed_enrollments", 0)
        full_journey.setdefault("completion_rate", 0.0)

    return {
        "journey": full_journey,
        "already_existed": False,
    }
