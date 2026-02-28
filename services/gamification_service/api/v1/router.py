from fastapi import APIRouter

from services.gamification_service.api.v1.endpoints import (
    admin_recalculate,
    admin_reward_organizations,
    admin_rewards,
    admin_user_progress,
    config,
    levels,
    rewards,
    user_progress,
)

router = APIRouter()

router.include_router(levels.router, tags=["Gamification - Levels"])
router.include_router(rewards.router, tags=["Gamification - Rewards Catalog"])
router.include_router(user_progress.router, tags=["Gamification - User Progress"])
router.include_router(admin_rewards.router, tags=["Gamification - Admin Rewards"])
router.include_router(admin_reward_organizations.router, tags=["Gamification - Reward Organizations"])
router.include_router(admin_user_progress.router, tags=["Gamification - Admin User Progress"])
router.include_router(config.router, tags=["Gamification - Config"])
router.include_router(admin_recalculate.router, tags=["Gamification - Admin Recalculate"])