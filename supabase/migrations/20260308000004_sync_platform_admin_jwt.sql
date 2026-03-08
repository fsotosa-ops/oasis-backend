-- =============================================================================
-- MIGRATION: Sync profiles.is_platform_admin → auth.users.raw_user_meta_data
-- =============================================================================
-- Problem:
--   When is_platform_admin is changed directly in public.profiles (via SQL,
--   migration, or factory_seed), auth.users.raw_user_meta_data is NOT updated.
--   The JWT is issued from raw_user_meta_data, so the user's JWT keeps showing
--   is_platform_admin: false even after promotion — until they logout/login.
--
-- Solution:
--   A trigger on public.profiles that syncs the flag to auth.users automatically,
--   regardless of whether the change comes from the API, a migration, or SQL.
--
-- After this migration:
--   - JWT stays in sync on every promotion/demotion
--   - No extra DB query needed in the backend middleware
--   - The DB fallback in security.py becomes a safety net only
-- =============================================================================

-- =============================================================================
-- 1. Trigger function
-- =============================================================================
CREATE OR REPLACE FUNCTION public.sync_platform_admin_to_auth()
RETURNS TRIGGER AS $$
BEGIN
    -- Only act when is_platform_admin actually changed
    IF NEW.is_platform_admin IS DISTINCT FROM OLD.is_platform_admin THEN
        UPDATE auth.users
        SET raw_user_meta_data = jsonb_set(
            COALESCE(raw_user_meta_data, '{}'),
            '{is_platform_admin}',
            to_jsonb(NEW.is_platform_admin)
        )
        WHERE id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 2. Trigger: fires only on is_platform_admin changes (not on every profile update)
-- =============================================================================
DROP TRIGGER IF EXISTS trg_sync_platform_admin_to_auth ON public.profiles;
CREATE TRIGGER trg_sync_platform_admin_to_auth
AFTER UPDATE OF is_platform_admin ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.sync_platform_admin_to_auth();

-- =============================================================================
-- 3. Backfill: sync existing platform admins directly into auth.users
--    NOTE: Cannot rely on the trigger here because the trigger checks
--    "IS DISTINCT FROM" — setting a column to its own value produces
--    OLD = NEW, so the condition is FALSE and auth.users is never updated.
--    We update auth.users directly instead.
-- =============================================================================
UPDATE auth.users
SET raw_user_meta_data = jsonb_set(
    COALESCE(raw_user_meta_data, '{}'),
    '{is_platform_admin}',
    'true'::jsonb
)
WHERE id IN (
    SELECT id FROM public.profiles WHERE is_platform_admin = TRUE
);

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ MIGRATION: sync_platform_admin_jwt applied' AS result;
SELECT email || ' → JWT synced' AS synced_admins
FROM public.profiles
WHERE is_platform_admin = TRUE;
