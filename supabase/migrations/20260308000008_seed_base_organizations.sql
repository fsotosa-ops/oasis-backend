-- =============================================================================
-- MIGRATION: Seed base organizations
-- =============================================================================
-- Ensures the two required base organizations exist after every 'supabase db push'.
-- oasis-community is created in 20260122000001_init_schema.sql (already exists).
-- fundacion-summer was missing — added here.
--
-- Both are idempotent (ON CONFLICT DO NOTHING).
-- =============================================================================

-- Fundación Summer: the provider org (content/programs owner)
INSERT INTO public.organizations (name, slug, type, description, settings)
VALUES (
    'Fundación Summer',
    'fundacion-summer',
    'provider',
    'Organización proveedora de programas educativos de Fundación Summer.',
    '{"is_default": false}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- Ensure gamification_config row for Fundación Summer
-- (trigger handles future orgs; base orgs need manual seeding)
INSERT INTO journeys.gamification_config (organization_id)
SELECT id FROM public.organizations WHERE slug = 'fundacion-summer'
ON CONFLICT (organization_id) DO NOTHING;

SELECT '✅ MIGRATION: base organizations seeded' AS result;
SELECT name, slug, type FROM public.organizations
WHERE slug IN ('oasis-community', 'fundacion-summer');
