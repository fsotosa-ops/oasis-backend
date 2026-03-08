-- =============================================================================
-- MIGRATION: Add 'gamification' audit category
-- =============================================================================
-- Separates gamification events (rewards, badges, XP) from journey events
-- so they can be filtered and reported independently in the audit trail.
--
-- Source of truth for all categories: supabase/scripts/audit_categories.sql
-- =============================================================================

INSERT INTO audit.categories (code, label, description) VALUES
    ('gamification', 'Gamificación', 'Recompensas, insignias y puntos de experiencia')
ON CONFLICT (code) DO NOTHING;

SELECT '✅ MIGRATION: gamification audit category added' AS result;
