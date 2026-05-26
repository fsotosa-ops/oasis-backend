-- =============================================================================
-- MIGRATION: platform_settings — singleton table for platform-wide configuration
-- =============================================================================
-- Stores platform-level settings editable by superadmins from the UI.
-- Uses a boolean PK trick (lock = TRUE) to enforce exactly one row.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.platform_settings (
    -- Singleton enforcer: only one row where lock = TRUE can exist
    lock                  BOOLEAN PRIMARY KEY DEFAULT TRUE,
    CONSTRAINT            platform_settings_one_row CHECK (lock = TRUE),

    -- Event Typeform URLs (standard for all events across all orgs)
    diagnosis_form_url    TEXT,
    closure_form_url      TEXT,

    -- Audit
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by            UUID REFERENCES public.profiles(id) ON DELETE SET NULL
);

-- Auto-update updated_at on any change
CREATE OR REPLACE TRIGGER platform_settings_updated_at
    BEFORE UPDATE ON public.platform_settings
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- RLS
ALTER TABLE public.platform_settings ENABLE ROW LEVEL SECURITY;

-- Any authenticated user can read (facilitators need to load form URLs)
DROP POLICY IF EXISTS "platform_settings_read" ON public.platform_settings;
CREATE POLICY "platform_settings_read" ON public.platform_settings
    FOR SELECT
    USING (auth.role() = 'authenticated');

-- Only platform admins can update
DROP POLICY IF EXISTS "platform_settings_admin_write" ON public.platform_settings;
CREATE POLICY "platform_settings_admin_write" ON public.platform_settings
    FOR UPDATE
    USING (public.get_is_platform_admin() = TRUE)
    WITH CHECK (public.get_is_platform_admin() = TRUE);

-- Grants
GRANT SELECT         ON public.platform_settings TO authenticated;
GRANT UPDATE         ON public.platform_settings TO authenticated;
GRANT ALL            ON public.platform_settings TO service_role;

-- Seed the single row (empty URLs — superadmin configures from the UI)
INSERT INTO public.platform_settings (lock, diagnosis_form_url, closure_form_url)
VALUES (TRUE, NULL, NULL)
ON CONFLICT (lock) DO NOTHING;

-- =============================================================================
SELECT '✅ MIGRATION: platform_settings singleton created and seeded' AS result;
