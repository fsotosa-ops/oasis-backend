-- =============================================================================
-- MIGRATION: Add points column to rewards_catalog
-- =============================================================================
-- Adds a first-class `points` field to rewards_catalog so that each reward
-- can carry its own point value (awarded when the reward is earned).
--
-- The unlock_condition JSONB field adopts a multi-condition structure:
--   {
--     "operator": "AND" | "OR",
--     "conditions": [
--       {"type": "profile_completion"},
--       {"type": "min_points", "value": 100},
--       {"type": "journey_completed", "journey_id": "<uuid>"}
--     ]
--   }
-- =============================================================================

ALTER TABLE journeys.rewards_catalog
ADD COLUMN points INTEGER NOT NULL DEFAULT 0;

SELECT '  points column added to rewards_catalog' AS detail;
