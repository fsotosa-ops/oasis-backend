-- =============================================================================
-- MIGRATION: Fix service_role table grants
-- =============================================================================
-- Problem:
--   After factory reset (DROP TABLE + supabase db push), the previous migration
--   20260130000001_cleanup_rls_policies.sql only granted privileges to
--   `authenticated`. The `service_role` role lost its table-level grants
--   because PostgreSQL GRANTs are tied to the table OID (not the name), so
--   they are lost when the table is dropped and recreated.
--
--   Supabase auto-grants service_role when tables are created via the dashboard,
--   but NOT when recreated via `supabase db push`. This migration makes the
--   grants explicit and idempotent.
--
-- Result:
--   The backend admin client (service_role) can SELECT/INSERT/UPDATE/DELETE
--   on all public app tables without hitting 403 db_insufficient_privilege.
-- =============================================================================

-- Schema usage
GRANT USAGE ON SCHEMA public TO service_role;
GRANT USAGE ON SCHEMA public TO anon;

-- Profiles
GRANT ALL ON TABLE public.profiles TO service_role;
GRANT SELECT ON TABLE public.profiles TO anon;

-- Organizations
GRANT ALL ON TABLE public.organizations TO service_role;
GRANT SELECT ON TABLE public.organizations TO anon;

-- Organization Members
GRANT ALL ON TABLE public.organization_members TO service_role;
GRANT SELECT ON TABLE public.organization_members TO anon;

-- Platform Admin Whitelist (internal — no anon access)
GRANT ALL ON TABLE public.platform_admin_whitelist TO service_role;

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ MIGRATION: service_role grants applied' AS result;
