-- =============================================================================
-- FACTORY SEED — Inserts minimum required data after 'supabase db push'
-- =============================================================================
-- Run AFTER applying all migrations via 'supabase db push'.
-- All operations are idempotent (ON CONFLICT / guarded by EXISTS).
--
-- Steps:
--   1. Fix service_role grants (lost when tables are dropped + recreated)
--   2. Seed all audit categories (inline — no \ir dependency)
--   3. Ensure base organizations exist
--   4. Seed admin whitelist
--   5. Ensure gamification_config rows for base orgs
--   6. Promote platform admins + assign ownership of both orgs
--   7. Verification summary
--
-- This file is self-contained: works in both psql and Supabase SQL Editor.
-- =============================================================================

-- =============================================================================
-- 1. Fix service_role grants (public + journeys + crm schemas)
-- =============================================================================
-- Supabase auto-grants service_role on tables created via dashboard, but NOT
-- via supabase db push. After factory reset the admin client gets 403.

-- public schema
GRANT USAGE ON SCHEMA public TO service_role;
GRANT USAGE ON SCHEMA public TO anon;
GRANT ALL ON TABLE public.profiles TO service_role;
GRANT ALL ON TABLE public.organizations TO service_role;
GRANT ALL ON TABLE public.organization_members TO service_role;
GRANT ALL ON TABLE public.platform_admin_whitelist TO service_role;
GRANT SELECT ON TABLE public.profiles TO anon;
GRANT SELECT ON TABLE public.organizations TO anon;
GRANT SELECT ON TABLE public.organization_members TO anon;

-- journeys schema
GRANT USAGE ON SCHEMA journeys TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA journeys TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA journeys GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA journeys GRANT ALL ON SEQUENCES TO service_role;

-- crm schema
GRANT USAGE ON SCHEMA crm TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA crm TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA crm GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA crm GRANT ALL ON SEQUENCES TO service_role;

-- =============================================================================
-- 2. Seed audit categories (inline — no \ir dependency)
-- =============================================================================
INSERT INTO audit.categories (code, label, description) VALUES
    ('auth',          'Seguridad',      'Logins, registro, logout'),
    ('org',           'Organización',   'Cambios en empresa, miembros e invitaciones'),
    ('billing',       'Facturación',    'Pagos y suscripciones'),
    ('journey',       'Experiencia',    'Avance de usuarios en journeys'),
    ('system',        'Sistema',        'Errores y tareas automáticas'),
    ('crm',           'CRM',            'Cambios en contactos, notas y tareas del CRM'),
    ('event',         'Evento',         'Creación, modificación y eliminación de eventos'),
    ('resource',      'Recurso',        'Acceso y gestión de recursos educativos'),
    ('gamification',  'Gamificación',   'Recompensas, insignias y puntos de experiencia')
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_community_org_id UUID;
    v_summer_org_id    UUID;
BEGIN

-- =============================================================================
-- 0. Backfill profiles for existing auth.users
--    factory_drop.sql wipes public.profiles but NOT auth.users.
--    handle_new_user only fires on INSERT into auth.users, so existing accounts
--    would be left without profiles after a reset. This recreates them.
-- =============================================================================
INSERT INTO public.profiles (id, email, full_name, avatar_url, metadata)
SELECT
    au.id,
    au.email,
    COALESCE(au.raw_user_meta_data->>'full_name', split_part(au.email, '@', 1)),
    au.raw_user_meta_data->>'avatar_url',
    COALESCE(au.raw_user_meta_data, '{}')
FROM auth.users au
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = au.id)
  AND au.email IS NOT NULL;

RAISE NOTICE '✅ Profiles backfilled for existing auth.users';

-- =============================================================================
-- 3. Ensure base organizations exist
--    These 2 orgs must always be present after every factory reset.
-- =============================================================================

-- Oasis Community: the open community every user is auto-joined to on signup
INSERT INTO public.organizations (name, slug, type, description, settings)
VALUES (
    'OASIS Community',
    'oasis-community',
    'community',
    'Comunidad abierta de OASIS. Todos los usuarios son miembros por defecto.',
    '{"is_default": true, "features": ["public_content"]}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- Fundación Summer: the provider org (Anthropic-equivalent for this platform)
INSERT INTO public.organizations (name, slug, type, description, settings)
VALUES (
    'Fundación Summer',
    'fundacion-summer',
    'provider',
    'Organización proveedora de programas educativos de Fundación Summer.',
    '{"is_default": false}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

SELECT id INTO v_community_org_id FROM public.organizations WHERE slug = 'oasis-community' LIMIT 1;
SELECT id INTO v_summer_org_id    FROM public.organizations WHERE slug = 'fundacion-summer' LIMIT 1;

IF v_community_org_id IS NULL THEN
    RAISE EXCEPTION 'oasis-community org not found after insert — this should not happen.';
END IF;
IF v_summer_org_id IS NULL THEN
    RAISE EXCEPTION 'fundacion-summer org not found after insert — this should not happen.';
END IF;

RAISE NOTICE '✅ Base orgs ready: oasis-community=%, fundacion-summer=%', v_community_org_id, v_summer_org_id;

-- =============================================================================
-- 4. Seed admin whitelist
--    Mirrors the whitelist seeded by migration 20260308000006.
--    Idempotent — safe to re-run after a factory reset.
-- =============================================================================
INSERT INTO public.platform_admin_whitelist (email, note) VALUES
    ('tech@fsummer.org',    'Tech lead — Oasis platform'),
    ('felipe@sumadots.com', 'Founder — Fundación Summer')
ON CONFLICT (email) DO NOTHING;

RAISE NOTICE '✅ Admin whitelist seeded';

-- =============================================================================
-- 5. Ensure gamification_config rows for base orgs
--    The auto-trigger (20260308000002) handles future orgs. Base orgs need
--    manual seeding because they're created before the trigger exists.
-- =============================================================================
INSERT INTO journeys.gamification_config (organization_id)
VALUES (v_community_org_id)
ON CONFLICT (organization_id) DO NOTHING;

INSERT INTO journeys.gamification_config (organization_id)
VALUES (v_summer_org_id)
ON CONFLICT (organization_id) DO NOTHING;

RAISE NOTICE '✅ gamification_config ensured for both base orgs';

-- =============================================================================
-- 5b. Ensure crm.organization_profiles rows for base orgs
--     The auto-trigger (20260308000011) handles future orgs. Base orgs need
--     manual seeding because they may be created before the trigger exists.
-- =============================================================================
INSERT INTO crm.organization_profiles (org_id)
VALUES (v_community_org_id)
ON CONFLICT (org_id) DO NOTHING;

INSERT INTO crm.organization_profiles (org_id)
VALUES (v_summer_org_id)
ON CONFLICT (org_id) DO NOTHING;

RAISE NOTICE '✅ crm.organization_profiles ensured for both base orgs';

-- =============================================================================
-- 6. Promote platform admins + assign ownership of BOTH base orgs
--    For existing accounts: promote and add memberships.
--    For new accounts: the whitelist trigger handles promotion on first login.
--    The org memberships below cover the case where admins already have accounts.
-- =============================================================================
UPDATE public.profiles
SET is_platform_admin = TRUE
WHERE email IN ('tech@fsummer.org', 'felipe@sumadots.com');

-- Ownership of Oasis Community
INSERT INTO public.organization_members (organization_id, user_id, role, status)
SELECT v_community_org_id, p.id, 'owner'::member_role, 'active'::membership_status
FROM public.profiles p
WHERE p.email IN ('tech@fsummer.org', 'felipe@sumadots.com')
ON CONFLICT (organization_id, user_id) DO UPDATE SET role = 'owner', status = 'active';

-- Ownership of Fundación Summer
INSERT INTO public.organization_members (organization_id, user_id, role, status)
SELECT v_summer_org_id, p.id, 'owner'::member_role, 'active'::membership_status
FROM public.profiles p
WHERE p.email IN ('tech@fsummer.org', 'felipe@sumadots.com')
ON CONFLICT (organization_id, user_id) DO UPDATE SET role = 'owner', status = 'active';

RAISE NOTICE '✅ Platform admins promoted + assigned as owners of both base orgs';

END $$;

-- =============================================================================
-- 7. Verification summary
-- =============================================================================
SELECT table_name, rows FROM (
    SELECT 'public.profiles'                    AS table_name, COUNT(*) AS rows FROM public.profiles
    UNION ALL
    SELECT 'public.organizations',               COUNT(*) FROM public.organizations
    UNION ALL
    SELECT 'public.organization_members',        COUNT(*) FROM public.organization_members
    UNION ALL
    SELECT 'public.platform_admin_whitelist',    COUNT(*) FROM public.platform_admin_whitelist
    UNION ALL
    SELECT 'audit.categories',                   COUNT(*) FROM audit.categories
    UNION ALL
    SELECT 'audit.logs',                         COUNT(*) FROM audit.logs
    UNION ALL
    SELECT 'journeys.gamification_config',       COUNT(*) FROM journeys.gamification_config
    UNION ALL
    SELECT 'crm.contacts',                       COUNT(*) FROM crm.contacts
    UNION ALL
    SELECT 'crm.organization_profiles',          COUNT(*) FROM crm.organization_profiles
) counts
ORDER BY table_name;

-- Show platform admins and their orgs
SELECT
    p.email,
    p.is_platform_admin,
    STRING_AGG(o.slug || ' (' || om.role || ')', ', ') AS org_memberships
FROM public.profiles p
LEFT JOIN public.organization_members om ON om.user_id = p.id AND om.status = 'active'
LEFT JOIN public.organizations o ON o.id = om.organization_id
WHERE p.is_platform_admin = TRUE
GROUP BY p.email, p.is_platform_admin;

SELECT '✅ Factory seed complete' AS status;
