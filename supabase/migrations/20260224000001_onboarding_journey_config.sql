-- =============================================================================
-- MIGRATION: Onboarding Journey config + legacy profile_completed cleanup
-- =============================================================================
-- Adds two optional columns to gamification_config so admins can link a
-- specific Journey and Step to "profile completion". When configured,
-- PATCH /crm/contacts/me will mark that step as completed (via the existing
-- journey trigger) instead of creating a standalone profile_completed activity.
--
-- Also cleans up existing duplicate / legacy data:
--   - points_ledger rows with reason = 'profile_completion'  (Python-created)
--   - user_activities rows with type = 'profile_completed'    (Python-created)
-- Going forward these are replaced by step_completed entries from the trigger.
-- =============================================================================

-- 1. Add new config columns (nullable → backwards-compatible)
ALTER TABLE journeys.gamification_config
    ADD COLUMN IF NOT EXISTS profile_completion_journey_id UUID
        REFERENCES journeys.journeys(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS profile_completion_step_id UUID
        REFERENCES journeys.steps(id) ON DELETE SET NULL;

-- 2. Clean up legacy Python-created entries (duplicate with step_completed)
DELETE FROM journeys.points_ledger
WHERE reason = 'profile_completion';

DELETE FROM journeys.user_activities
WHERE type = 'profile_completed';

-- =============================================================================
SELECT '✅ MIGRATION: onboarding_journey_config applied' AS result;
SELECT '  - profile_completion_journey_id added to gamification_config' AS detail;
SELECT '  - profile_completion_step_id added to gamification_config' AS detail;
SELECT '  - Legacy profile_completed activities removed' AS detail;
SELECT '  - Legacy profile_completion ledger entries removed' AS detail;
