-- =============================================================================
-- MIGRATION: Add profile_completion_points to gamification_config
-- =============================================================================
-- Allows admins to configure how many points a user earns when completing
-- their profile information for the first time.
-- =============================================================================

ALTER TABLE journeys.gamification_config
ADD COLUMN profile_completion_points INTEGER NOT NULL DEFAULT 0;

SELECT '  profile_completion_points column added to gamification_config' AS detail;