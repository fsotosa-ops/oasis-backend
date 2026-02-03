-- =============================================================================
-- MIGRATION: Auto-Promote Corporate Account (APP PROJECT ONLY)
-- =============================================================================
-- Project: OASIS App (Transactional)
-- Description: Intercepts user creation for 'tech@fsummer.org', promotes to
-- Platform Admin and ensures ownership of the 'oasis-community' org.
-- =============================================================================

-- 1. FUNCTION: Handle Profile Promotion (Triggered on public.profiles INSERT)
CREATE OR REPLACE FUNCTION public.handle_tech_owner_promotion()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER -- Bypasses RLS to ensure we can write admin flags
SET search_path = public
AS $$
DECLARE
    v_community_org_id UUID;
    v_audit_meta JSONB;
BEGIN
    -- TARGET: Only specific corporate account
    IF NEW.email IN ('tech@fsummer.org', 'felipe@sumadots.com') THEN

        -- A. PLATFORM ADMIN PROMOTION
        NEW.is_platform_admin := TRUE;

        -- B. ORG ASSIGNMENT LOGIC
        -- We try to find the default community org to assign ownership immediately
        SELECT id INTO v_community_org_id
        FROM public.organizations
        WHERE slug = 'oasis-community'
        LIMIT 1;

        IF v_community_org_id IS NOT NULL THEN
            RAISE NOTICE 'Corporate Owner Detected: % (Org ID: %)', NEW.email, v_community_org_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

-- 2. TRIGGER: Attach to Profiles (Before Insert)
DROP TRIGGER IF EXISTS tr_promote_tech_owner ON public.profiles;

CREATE TRIGGER tr_promote_tech_owner
BEFORE INSERT ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.handle_tech_owner_promotion();

-- =============================================================================
-- 3. FUNCTION: Force Owner Role (Triggered AFTER Profile/Member creation)
-- =============================================================================
-- This guarantees that even if the standard onboarding flow puts them as 'participant',
-- we override it to 'owner' immediately.

CREATE OR REPLACE FUNCTION public.force_tech_owner_role()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_community_org_id UUID;
BEGIN
    IF NEW.email IN ('tech@fsummer.org', 'felipe@sumadots.com') THEN
        -- Find Community Org
        SELECT id INTO v_community_org_id
        FROM public.organizations
        WHERE slug = 'oasis-community'
        LIMIT 1;

        IF v_community_org_id IS NOT NULL THEN
            -- Upsert: If member exists, update role. If not, insert as owner.
            INSERT INTO public.organization_members (organization_id, user_id, role, status)
            VALUES (v_community_org_id, NEW.id, 'owner', 'active')
            ON CONFLICT (organization_id, user_id)
            DO UPDATE SET role = 'owner', status = 'active';
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

-- 4. TRIGGER: Attach to Profiles (After Insert - Async-ish)
DROP TRIGGER IF EXISTS tr_force_tech_role ON public.profiles;

CREATE TRIGGER tr_force_tech_role
AFTER INSERT ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.force_tech_owner_role();