-- =============================================================================
-- MIGRATION: Cleanup and Consolidate RLS Policies
-- =============================================================================
-- This migration:
-- 1. Drops ALL existing RLS policies to avoid conflicts
-- 2. Creates clean, consolidated policies
-- 3. Ensures proper GRANTs for authenticated users
-- 4. Promotes felipe@sumadots.com as platform admin
-- =============================================================================

-- =============================================================================
-- 1. GRANTS - Allow authenticated users to interact with tables
-- =============================================================================
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON TABLE public.profiles TO authenticated;
GRANT ALL ON TABLE public.organizations TO authenticated;
GRANT ALL ON TABLE public.organization_members TO authenticated;

-- =============================================================================
-- 2. DROP ALL EXISTING POLICIES (Clean slate)
-- =============================================================================

-- Profiles policies
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_select_platform_admin" ON public.profiles;
DROP POLICY IF EXISTS "profiles_select_org_members" ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_platform_admin" ON public.profiles;
DROP POLICY IF EXISTS "profiles_read_policy" ON public.profiles;

-- Organizations policies
DROP POLICY IF EXISTS "organizations_select_community" ON public.organizations;
DROP POLICY IF EXISTS "organizations_select_member" ON public.organizations;
DROP POLICY IF EXISTS "organizations_select_platform_admin" ON public.organizations;
DROP POLICY IF EXISTS "organizations_update_owner" ON public.organizations;
DROP POLICY IF EXISTS "organizations_update_platform_admin" ON public.organizations;
DROP POLICY IF EXISTS "organizations_insert_platform_admin" ON public.organizations;
DROP POLICY IF EXISTS "organizations_delete_platform_admin" ON public.organizations;
DROP POLICY IF EXISTS "orgs_read_member" ON public.organizations;
DROP POLICY IF EXISTS "orgs_read_admin" ON public.organizations;
DROP POLICY IF EXISTS "read_organizations" ON public.organizations;

-- Organization members policies
DROP POLICY IF EXISTS "org_members_select_same_org" ON public.organization_members;
DROP POLICY IF EXISTS "org_members_select_platform_admin" ON public.organization_members;
DROP POLICY IF EXISTS "org_members_insert_admin" ON public.organization_members;
DROP POLICY IF EXISTS "org_members_update_admin" ON public.organization_members;
DROP POLICY IF EXISTS "org_members_delete" ON public.organization_members;
DROP POLICY IF EXISTS "members_read_own" ON public.organization_members;
DROP POLICY IF EXISTS "members_read_admin" ON public.organization_members;
DROP POLICY IF EXISTS "read_members" ON public.organization_members;

-- =============================================================================
-- 3. HELPER FUNCTIONS (Recreate for safety)
-- =============================================================================

-- Check if current user is platform admin (secure version)
CREATE OR REPLACE FUNCTION public.is_platform_admin()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
BEGIN
    RETURN COALESCE(
        (SELECT is_platform_admin FROM public.profiles WHERE id = auth.uid()),
        FALSE
    );
END;
$$;

-- Get organization IDs where current user is an active member
CREATE OR REPLACE FUNCTION public.get_user_org_ids()
RETURNS SETOF UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT organization_id
    FROM public.organization_members
    WHERE user_id = auth.uid()
    AND status = 'active';
$$;

-- Get current user's role in a specific organization
CREATE OR REPLACE FUNCTION public.get_user_role_in_org(org_id UUID)
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT role::text
    FROM public.organization_members
    WHERE user_id = auth.uid()
    AND organization_id = org_id
    AND status = 'active'
    LIMIT 1;
$$;

-- Check if user is owner or admin in an organization
CREATE OR REPLACE FUNCTION public.is_org_admin(org_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE user_id = auth.uid()
        AND organization_id = org_id
        AND role IN ('owner', 'admin')
        AND status = 'active'
    );
$$;

-- =============================================================================
-- 4. PROFILES POLICIES
-- =============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- SELECT: Users can see their own profile
CREATE POLICY "profiles_select_own" ON public.profiles
FOR SELECT USING (id = auth.uid());

-- SELECT: Platform admins can see all profiles
CREATE POLICY "profiles_select_admin" ON public.profiles
FOR SELECT USING (public.is_platform_admin() = TRUE);

-- SELECT: Users can see profiles of members in their organizations
CREATE POLICY "profiles_select_org_members" ON public.profiles
FOR SELECT USING (
    id IN (
        SELECT om.user_id
        FROM public.organization_members om
        WHERE om.organization_id IN (SELECT public.get_user_org_ids())
        AND om.status = 'active'
    )
);

-- UPDATE: Users can update their own profile (except is_platform_admin)
CREATE POLICY "profiles_update_own" ON public.profiles
FOR UPDATE USING (id = auth.uid())
WITH CHECK (
    id = auth.uid()
    AND is_platform_admin = (SELECT is_platform_admin FROM public.profiles WHERE id = auth.uid())
);

-- UPDATE: Platform admins can update any profile
CREATE POLICY "profiles_update_admin" ON public.profiles
FOR UPDATE USING (public.is_platform_admin() = TRUE);

-- =============================================================================
-- 5. ORGANIZATIONS POLICIES
-- =============================================================================
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

-- SELECT: Members can see their organizations
CREATE POLICY "organizations_select_member" ON public.organizations
FOR SELECT USING (id IN (SELECT public.get_user_org_ids()));

-- SELECT: Anyone can see community organizations
CREATE POLICY "organizations_select_community" ON public.organizations
FOR SELECT USING (type = 'community');

-- SELECT: Platform admins can see all organizations
CREATE POLICY "organizations_select_admin" ON public.organizations
FOR SELECT USING (public.is_platform_admin() = TRUE);

-- UPDATE: Owners can update their organization
CREATE POLICY "organizations_update_owner" ON public.organizations
FOR UPDATE USING (
    EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE user_id = auth.uid()
        AND organization_id = id
        AND role = 'owner'
        AND status = 'active'
    )
);

-- UPDATE: Platform admins can update any organization
CREATE POLICY "organizations_update_admin" ON public.organizations
FOR UPDATE USING (public.is_platform_admin() = TRUE);

-- INSERT: Platform admins can create organizations
CREATE POLICY "organizations_insert_admin" ON public.organizations
FOR INSERT WITH CHECK (public.is_platform_admin() = TRUE);

-- DELETE: Platform admins can delete organizations (except community type)
CREATE POLICY "organizations_delete_admin" ON public.organizations
FOR DELETE USING (
    public.is_platform_admin() = TRUE
    AND type != 'community'
);

-- =============================================================================
-- 6. ORGANIZATION MEMBERS POLICIES
-- =============================================================================
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;

-- SELECT: Users can see members in their organizations
CREATE POLICY "members_select_same_org" ON public.organization_members
FOR SELECT USING (organization_id IN (SELECT public.get_user_org_ids()));

-- SELECT: Platform admins can see all memberships
CREATE POLICY "members_select_admin" ON public.organization_members
FOR SELECT USING (public.is_platform_admin() = TRUE);

-- INSERT: Owners/Admins can add members to their organizations
CREATE POLICY "members_insert_org_admin" ON public.organization_members
FOR INSERT WITH CHECK (
    public.is_org_admin(organization_id) = TRUE
    OR public.is_platform_admin() = TRUE
);

-- UPDATE: Owners/Admins can update memberships in their organizations
CREATE POLICY "members_update_org_admin" ON public.organization_members
FOR UPDATE USING (
    public.is_org_admin(organization_id) = TRUE
    OR public.is_platform_admin() = TRUE
);

-- DELETE: Users can leave orgs (except community), Admins can remove members
CREATE POLICY "members_delete" ON public.organization_members
FOR DELETE USING (
    -- Self-removal (user leaving an org, except community)
    (
        user_id = auth.uid()
        AND NOT EXISTS (
            SELECT 1 FROM public.organizations
            WHERE id = organization_id AND type = 'community'
        )
    )
    -- Org admin removing someone
    OR public.is_org_admin(organization_id) = TRUE
    -- Platform admin
    OR public.is_platform_admin() = TRUE
);

-- =============================================================================
-- 7. PROMOTE PLATFORM ADMINS
-- =============================================================================
-- This runs on existing data; if the user doesn't exist yet, it's handled by trigger
UPDATE public.profiles
SET is_platform_admin = TRUE
WHERE email IN ('tech@fsummer.org', 'felipe@sumadots.com');

-- Ensure platform admins are owners of oasis-community if they exist
INSERT INTO public.organization_members (organization_id, user_id, role, status)
SELECT
    o.id,
    p.id,
    'owner'::member_role,
    'active'::membership_status
FROM public.profiles p
CROSS JOIN public.organizations o
WHERE p.email IN ('tech@fsummer.org', 'felipe@sumadots.com')
AND o.slug = 'oasis-community'
ON CONFLICT (organization_id, user_id)
DO UPDATE SET role = 'owner', status = 'active';

-- =============================================================================
-- 8. BACKWARD COMPATIBILITY ALIASES
-- =============================================================================
-- Keep is_admin_secure() as alias for journey schema compatibility
CREATE OR REPLACE FUNCTION public.is_admin_secure()
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT public.is_platform_admin();
$$;

-- Keep get_is_platform_admin() as alias
CREATE OR REPLACE FUNCTION public.get_is_platform_admin()
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT public.is_platform_admin();
$$;

-- Keep get_my_org_ids() as alias
CREATE OR REPLACE FUNCTION public.get_my_org_ids()
RETURNS SETOF UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT public.get_user_org_ids();
$$;

-- Keep get_my_role_in_org() as alias
CREATE OR REPLACE FUNCTION public.get_my_role_in_org(org_id UUID)
RETURNS member_role
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT role FROM public.organization_members
    WHERE user_id = auth.uid()
    AND organization_id = org_id
    AND status = 'active'
    LIMIT 1;
$$;

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ RLS Policies Cleaned Up and Consolidated' as status;
