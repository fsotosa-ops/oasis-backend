-- =============================================================================
-- MIGRATION: Platform Admin Whitelist + Auto-Promote on First Login
-- =============================================================================
-- Problem:
--   When a platform admin logs in via Google OAuth for the first time,
--   Supabase creates auth.users → triggers create profiles with
--   is_platform_admin = FALSE → JWT doesn't have admin access.
--
-- Solution:
--   1. A table `public.platform_admin_whitelist` holds trusted admin emails.
--   2. An AFTER INSERT trigger on public.profiles checks the whitelist and
--      promotes the user immediately (same transaction as signup).
--   3. The existing trg_sync_platform_admin_to_auth then syncs profiles →
--      auth.users.raw_user_meta_data so the JWT reflects the promotion.
--
-- Result:
--   On first Google OAuth login, the JWT already has is_platform_admin: true.
--   No manual promotion needed after factory reset.
--
-- To add a new admin:
--   INSERT INTO public.platform_admin_whitelist (email) VALUES ('new@admin.com');
-- =============================================================================

-- =============================================================================
-- 1. Whitelist table
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.platform_admin_whitelist (
    email TEXT PRIMARY KEY,
    note  TEXT  -- optional: why this email is an admin
);

COMMENT ON TABLE public.platform_admin_whitelist IS
    'Emails that auto-promote to platform_admin on first login. '
    'Managed by factory_seed.sql — do not edit manually in production.';

-- =============================================================================
-- 2. Trigger function: fires AFTER a profile is created
-- =============================================================================
CREATE OR REPLACE FUNCTION public.auto_promote_platform_admin()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if this email is in the admin whitelist
    IF EXISTS (
        SELECT 1 FROM public.platform_admin_whitelist WHERE email = NEW.email
    ) THEN
        -- Update the profile (triggers trg_sync_platform_admin_to_auth)
        UPDATE public.profiles
        SET is_platform_admin = TRUE
        WHERE id = NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- =============================================================================
-- 3. Trigger: fires after every new profile row
-- =============================================================================
DROP TRIGGER IF EXISTS trg_auto_promote_platform_admin ON public.profiles;
CREATE TRIGGER trg_auto_promote_platform_admin
AFTER INSERT ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.auto_promote_platform_admin();

-- =============================================================================
-- 4. Seed initial whitelist entries (idempotent)
-- =============================================================================
INSERT INTO public.platform_admin_whitelist (email, note) VALUES
    ('tech@fsummer.org',    'Tech lead — Oasis platform'),
    ('felipe@sumadots.com', 'Consultant — Growth Social Impact')
ON CONFLICT (email) DO NOTHING;

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ MIGRATION: admin_whitelist_auto_promote applied' AS result;
SELECT email || ' → in whitelist' AS whitelisted_admins
FROM public.platform_admin_whitelist;
