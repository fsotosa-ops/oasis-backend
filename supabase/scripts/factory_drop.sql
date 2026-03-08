-- =============================================================================
-- FACTORY DROP — Destroys all application schemas and objects
-- =============================================================================
-- USE ONLY for dev/testing. DO NOT run in production without intent.
--
-- Drop order respects FK dependencies (verified against audit_fk_rules.csv):
--   auth.users triggers (explicit) → app schemas CASCADE → public tables → functions → types
--
-- Schema drop notes:
--   journeys CASCADE → removes enrollments.event_id FK → public.org_events
--   crm CASCADE      → cascades to trg_auto_create_crm_contact on auth.users
--   audit CASCADE    → cascades to trg_audit_organizations, trg_audit_organization_members,
--                      trg_audit_org_events (cross-schema triggers on public/crm tables)
--
-- Does NOT touch: auth, storage, realtime, supabase_* (Supabase system schemas)
-- =============================================================================

-- =============================================================================
-- 1. Triggers on auth.users that reference public functions
--    (must drop explicitly — public schema is not dropped)
-- =============================================================================
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
-- trg_auto_create_crm_contact → dropped automatically by DROP SCHEMA crm CASCADE

-- =============================================================================
-- 2. Application schemas (CASCADE handles all internal objects + cross-schema FKs)
-- =============================================================================
DROP SCHEMA IF EXISTS webhooks  CASCADE;
DROP SCHEMA IF EXISTS resources CASCADE;
DROP SCHEMA IF EXISTS journeys  CASCADE;  -- BEFORE crm: enrollments.event_id → public.org_events
DROP SCHEMA IF EXISTS crm       CASCADE;  -- CASCADE drops trg_auto_create_crm_contact on auth.users
DROP SCHEMA IF EXISTS audit     CASCADE;  -- CASCADE drops trg_audit_* triggers on public tables

-- =============================================================================
-- 3. Public tables (in FK dependency order)
--    public.org_events has FK → organizations (CASCADE) and → journeys.journeys (SET NULL, already dropped)
-- =============================================================================
DROP TABLE IF EXISTS public.org_events                CASCADE;  -- ghost table cleanup
DROP TABLE IF EXISTS public.organization_members      CASCADE;
DROP TABLE IF EXISTS public.organizations             CASCADE;
DROP TABLE IF EXISTS public.platform_admin_whitelist  CASCADE;
DROP TABLE IF EXISTS public.profiles                  CASCADE;

-- =============================================================================
-- 4. Public functions (triggers on dropped tables are already gone)
-- =============================================================================

-- Auth audit helpers
DROP FUNCTION IF EXISTS public.log_register(TEXT)          CASCADE;
DROP FUNCTION IF EXISTS public.log_logout()                CASCADE;
DROP FUNCTION IF EXISTS public.log_login(TEXT, TEXT)       CASCADE;
DROP FUNCTION IF EXISTS public.log_auth_event(TEXT, JSONB) CASCADE;

-- Cross-schema queries
DROP FUNCTION IF EXISTS public.get_contact_events(UUID)                              CASCADE;
DROP FUNCTION IF EXISTS public.admin_update_profile(UUID, TEXT, TEXT, BOOLEAN)       CASCADE;

-- RLS helpers (aliases first, then originals)
DROP FUNCTION IF EXISTS public.is_admin_secure()           CASCADE;
DROP FUNCTION IF EXISTS public.is_admin()                  CASCADE;
DROP FUNCTION IF EXISTS public.is_platform_admin()         CASCADE;
DROP FUNCTION IF EXISTS public.is_org_admin(UUID)          CASCADE;
DROP FUNCTION IF EXISTS public.get_is_platform_admin()     CASCADE;
DROP FUNCTION IF EXISTS public.get_my_org_ids()            CASCADE;
DROP FUNCTION IF EXISTS public.get_my_role_in_org(UUID)    CASCADE;
DROP FUNCTION IF EXISTS public.get_user_org_ids()          CASCADE;
DROP FUNCTION IF EXISTS public.get_user_role_in_org(UUID)  CASCADE;

-- Trigger functions (profiles triggers dropped with profiles table above)
DROP FUNCTION IF EXISTS public.auto_promote_platform_admin()  CASCADE;
DROP FUNCTION IF EXISTS public.handle_tech_owner_promotion()  CASCADE;
DROP FUNCTION IF EXISTS public.force_tech_owner_role()        CASCADE;
DROP FUNCTION IF EXISTS public.prevent_admin_escalation()     CASCADE;
DROP FUNCTION IF EXISTS public.protect_sensitive_columns()    CASCADE;
DROP FUNCTION IF EXISTS public.handle_new_user()              CASCADE;

-- Utility trigger functions
DROP FUNCTION IF EXISTS public.set_updated_at()              CASCADE;
DROP FUNCTION IF EXISTS public.update_updated_at_column()    CASCADE;

-- =============================================================================
-- 5. Custom ENUM types (CASCADE removes dependent columns in already-dropped tables)
-- =============================================================================
DROP TYPE IF EXISTS public.org_type          CASCADE;
DROP TYPE IF EXISTS public.member_role       CASCADE;
DROP TYPE IF EXISTS public.membership_status CASCADE;
DROP TYPE IF EXISTS public.account_status    CASCADE;

-- =============================================================================
-- DONE — Database is clean.
-- Next step: run 'supabase db push' to re-apply all migrations.
-- =============================================================================
SELECT '✅ Factory drop complete. Run supabase db push to re-apply migrations.' AS status;
