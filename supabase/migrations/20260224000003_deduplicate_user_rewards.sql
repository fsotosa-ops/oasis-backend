-- =============================================================================
-- MIGRATION: Deduplicate user_rewards + add UNIQUE constraint
-- =============================================================================
-- user_rewards had no UNIQUE(user_id, reward_id) constraint. Some rewards were
-- granted multiple times (e.g., once via Python profile_completion path and once
-- via SQL trigger on journey completion). get_user_rewards() deduplicates on
-- read (already deployed), but this migration:
--   1. Cleans existing duplicate rows (keeps earliest grant)
--   2. Adds DB-level constraint to prevent future duplicates
-- =============================================================================

-- 1. Delete duplicate user_rewards, keep earliest grant per (user_id, reward_id)
DELETE FROM journeys.user_rewards
WHERE id NOT IN (
    SELECT DISTINCT ON (user_id, reward_id) id
    FROM journeys.user_rewards
    ORDER BY user_id, reward_id, earned_at ASC
);

-- 2. Prevent future duplicates
ALTER TABLE journeys.user_rewards
    ADD CONSTRAINT uq_user_rewards_user_reward
    UNIQUE (user_id, reward_id);

-- =============================================================================
SELECT '✅ MIGRATION: deduplicate_user_rewards applied' AS result;
SELECT '  - Duplicate user_rewards rows removed (kept earliest per user+reward)' AS detail;
SELECT '  - UNIQUE constraint on (user_id, reward_id) added' AS detail;
