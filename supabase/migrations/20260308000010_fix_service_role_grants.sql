-- =============================================================================
-- MIGRATION: Fix service_role table grants (public + journeys + crm schemas)
-- =============================================================================
-- Problem:
--   After factory reset (DROP TABLE + supabase db push), service_role loses its
--   table-level GRANTs because PostgreSQL GRANTs are tied to the table OID (not
--   the name). Supabase auto-grants service_role only for dashboard-created tables,
--   NOT for tables created via `supabase db push`.
--
--   Additionally, tables created AFTER a schema-level `GRANT ALL ON ALL TABLES`
--   statement (e.g. journey_organizations created after 20260124182603) are NOT
--   covered unless ALTER DEFAULT PRIVILEGES is set for the schema.
--
-- Root causes fixed here:
--   1. public schema: 20260130000001 granted only to `authenticated`
--   2. journeys schema: journey_organizations created after the schema-level GRANT;
--      no ALTER DEFAULT PRIVILEGES in journeys schema
--   3. crm schema: same pattern — tables created after schema-level GRANT
--
-- Result:
--   The backend admin client (service_role) can SELECT/INSERT/UPDATE/DELETE
--   on all app tables without hitting 403 db_insufficient_privilege.
-- =============================================================================

-- =============================================================================
-- public schema
-- =============================================================================
GRANT USAGE ON SCHEMA public TO service_role;
GRANT USAGE ON SCHEMA public TO anon;

GRANT ALL ON TABLE public.profiles TO service_role;
GRANT SELECT ON TABLE public.profiles TO anon;

GRANT ALL ON TABLE public.organizations TO service_role;
GRANT SELECT ON TABLE public.organizations TO anon;

GRANT ALL ON TABLE public.organization_members TO service_role;
GRANT SELECT ON TABLE public.organization_members TO anon;

GRANT ALL ON TABLE public.platform_admin_whitelist TO service_role;

-- =============================================================================
-- journeys schema
-- =============================================================================
GRANT USAGE ON SCHEMA journeys TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA journeys TO service_role;
-- Cover tables created by future migrations in this schema
ALTER DEFAULT PRIVILEGES IN SCHEMA journeys GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA journeys GRANT ALL ON SEQUENCES TO service_role;

-- =============================================================================
-- crm schema
-- =============================================================================
GRANT USAGE ON SCHEMA crm TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA crm TO service_role;
-- Cover tables created by future migrations in this schema
ALTER DEFAULT PRIVILEGES IN SCHEMA crm GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA crm GRANT ALL ON SEQUENCES TO service_role;

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ MIGRATION: service_role grants applied (public + journeys + crm)' AS result;
