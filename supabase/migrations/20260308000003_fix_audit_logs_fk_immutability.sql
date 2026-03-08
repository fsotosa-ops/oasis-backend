-- =============================================================================
-- MIGRATION: Fix FK conflict between audit.logs immutability and ON DELETE SET NULL
-- =============================================================================
-- Problem:
--   audit.logs has an immutability trigger (prevent_log_modification) that blocks
--   all UPDATE and DELETE. But audit.logs.organization_id and actor_id are defined
--   as REFERENCES ... ON DELETE SET NULL. When an org or user is deleted, Postgres
--   tries to SET NULL those columns → immutability trigger fires → ERROR.
--
-- Fix:
--   Drop the FK constraints on organization_id and actor_id.
--   The columns keep their UUID values as immutable historical snapshots.
--   audit.logs.category_code FK is kept (categories are never deleted).
-- =============================================================================

ALTER TABLE audit.logs
    DROP CONSTRAINT IF EXISTS logs_organization_id_fkey;

ALTER TABLE audit.logs
    DROP CONSTRAINT IF EXISTS logs_actor_id_fkey;

-- =============================================================================
-- DONE
-- =============================================================================
COMMENT ON COLUMN audit.logs.organization_id IS
    'Snapshot UUID of the org at log time. No FK — audit logs are immutable.';
COMMENT ON COLUMN audit.logs.actor_id IS
    'Snapshot UUID of the actor at log time. No FK — audit logs are immutable.';

SELECT '✅ MIGRATION: audit_logs FK immutability conflict fixed' AS result;
