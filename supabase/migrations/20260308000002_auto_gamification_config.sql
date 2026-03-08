-- =============================================================================
-- MIGRATION: Auto-create gamification_config for new organizations
-- =============================================================================
-- Root cause fix: gamification UI invisible for orgs created after migration
-- 20260213000001 because the config row was never auto-inserted.
--
-- Chain of failure (documented in user.py onboarding-check endpoint):
--   GET /journeys/me/onboarding-check
--   → gamification_config row missing → profile_completion_journey_id = NULL
--   → should_show = false → gamification never appears
--
-- Fix:
--   1. Trigger: new org INSERT → auto-insert gamification_config row
--   2. Backfill: existing orgs without a config row get one now
--
-- NOTE: profile_completion_journey_id remains NULL until an admin assigns
--       which journey to use as the onboarding flow via the UI.
-- =============================================================================

-- =============================================================================
-- 1. Trigger function
-- =============================================================================
CREATE OR REPLACE FUNCTION journeys.handle_new_org_gamification()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO journeys.gamification_config (organization_id)
    VALUES (NEW.id)
    ON CONFLICT (organization_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 2. Trigger: AFTER INSERT on organizations
-- =============================================================================
DROP TRIGGER IF EXISTS trg_auto_gamification_config ON public.organizations;
CREATE TRIGGER trg_auto_gamification_config
AFTER INSERT ON public.organizations
FOR EACH ROW EXECUTE FUNCTION journeys.handle_new_org_gamification();

-- =============================================================================
-- 3. Backfill: orgs that already exist but have no config row
-- =============================================================================
INSERT INTO journeys.gamification_config (organization_id)
SELECT id FROM public.organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM journeys.gamification_config gc
    WHERE gc.organization_id = o.id
);

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ MIGRATION: auto_gamification_config applied' AS result;
SELECT COUNT(*) || ' org(s) now have a gamification_config row' AS detail
FROM journeys.gamification_config;
