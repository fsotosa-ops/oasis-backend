-- =============================================================================
-- MIGRATION: Row Level Security Policies
-- =============================================================================
-- Defines WHO can do WHAT on each table.
-- Follows principle of least privilege with defense in depth.
-- =============================================================================

-- =============================================================================
-- 1. PROFILES POLICIES
-- =============================================================================

-- Users can always see their own profile
CREATE POLICY "profiles_select_own"
ON public.profiles FOR SELECT
USING (auth.uid() = id);

-- Platform Admins can see all profiles
CREATE POLICY "profiles_select_platform_admin"
ON public.profiles FOR SELECT
USING (public.get_is_platform_admin() = TRUE);

-- Users can see profiles of people in their organizations
CREATE POLICY "profiles_select_org_members"
ON public.profiles FOR SELECT
USING (
    id IN (
        SELECT DISTINCT om2.user_id
        FROM public.organization_members om1
        INNER JOIN public.organization_members om2
            ON om1.organization_id = om2.organization_id
        WHERE om1.user_id = auth.uid()
            AND om1.status = 'active'
            AND om2.status = 'active'
    )
);

-- Users can update their own profile (except is_platform_admin)
CREATE POLICY "profiles_update_own"
ON public.profiles FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (
    auth.uid() = id
    -- Prevent self-promotion to platform admin
    AND (is_platform_admin = (SELECT is_platform_admin FROM public.profiles WHERE id = auth.uid()))
);

-- Platform Admins can update any profile
CREATE POLICY "profiles_update_platform_admin"
ON public.profiles FOR UPDATE
USING (public.get_is_platform_admin() = TRUE);

-- =============================================================================
-- 2. ORGANIZATIONS POLICIES
-- =============================================================================

-- Anyone can see community organizations (public)
CREATE POLICY "organizations_select_community"
ON public.organizations FOR SELECT
USING (type = 'community');

-- Members can see their organizations
CREATE POLICY "organizations_select_member"
ON public.organizations FOR SELECT
USING (id IN (SELECT public.get_my_org_ids()));

-- Platform Admins can see all organizations
CREATE POLICY "organizations_select_platform_admin"
ON public.organizations FOR SELECT
USING (public.get_is_platform_admin() = TRUE);

-- Owners can update their organization
CREATE POLICY "organizations_update_owner"
ON public.organizations FOR UPDATE
USING (
    id IN (
        SELECT organization_id
        FROM public.organization_members
        WHERE user_id = auth.uid()
        AND role = 'owner'
        AND status = 'active'
    )
);

-- Platform Admins can update any organization
CREATE POLICY "organizations_update_platform_admin"
ON public.organizations FOR UPDATE
USING (public.get_is_platform_admin() = TRUE);

-- Platform Admins can insert organizations
CREATE POLICY "organizations_insert_platform_admin"
ON public.organizations FOR INSERT
WITH CHECK (public.get_is_platform_admin() = TRUE);

-- Platform Admins can delete organizations (except community)
CREATE POLICY "organizations_delete_platform_admin"
ON public.organizations FOR DELETE
USING (
    public.get_is_platform_admin() = TRUE
    AND type != 'community'
);

-- =============================================================================
-- 3. ORGANIZATION MEMBERS POLICIES
-- =============================================================================

-- Members can see other members in their organizations
CREATE POLICY "org_members_select_same_org"
ON public.organization_members FOR SELECT
USING (organization_id IN (SELECT public.get_my_org_ids()));

-- Platform Admins can see all memberships
CREATE POLICY "org_members_select_platform_admin"
ON public.organization_members FOR SELECT
USING (public.get_is_platform_admin() = TRUE);

-- Owners and Admins can add members to their organizations
CREATE POLICY "org_members_insert_admin"
ON public.organization_members FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.organization_members AS my_membership
        WHERE my_membership.user_id = auth.uid()
        AND my_membership.organization_id = organization_id
        AND my_membership.role IN ('owner', 'admin')
        AND my_membership.status = 'active'
    )
    OR public.get_is_platform_admin() = TRUE
);

-- Owners and Admins can update memberships
-- (Role hierarchy enforced by backend)
CREATE POLICY "org_members_update_admin"
ON public.organization_members FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM public.organization_members AS my_membership
        WHERE my_membership.user_id = auth.uid()
        AND my_membership.organization_id = public.organization_members.organization_id
        AND my_membership.role IN ('owner', 'admin')
        AND my_membership.status = 'active'
    )
    OR public.get_is_platform_admin() = TRUE
);

-- Users can remove themselves (leave org)
-- Admins can remove others (hierarchy enforced by backend)
CREATE POLICY "org_members_delete"
ON public.organization_members FOR DELETE
USING (
    -- Self-removal (except from community)
    (
        user_id = auth.uid()
        AND organization_id != '00000000-0000-0000-0000-000000000001'::uuid
    )
    -- Admin removal
    OR EXISTS (
        SELECT 1 FROM public.organization_members AS my_membership
        WHERE my_membership.user_id = auth.uid()
        AND my_membership.organization_id = public.organization_members.organization_id
        AND my_membership.role IN ('owner', 'admin')
        AND my_membership.status = 'active'
    )
    -- Platform admin
    OR public.get_is_platform_admin() = TRUE
);

-- =============================================================================
-- DONE
-- =============================================================================
COMMENT ON SCHEMA public IS 'OASIS Platform - Multi-tenant with RLS';



-- =============================================================================
-- V2 UPDATE FUNCTION admin_update_profile
-- =============================================================================
CREATE OR REPLACE FUNCTION admin_update_profile(                                        
    p_user_id UUID,                                                                       
    p_full_name TEXT DEFAULT NULL,                                                        
    p_status TEXT DEFAULT NULL,                                                           
    p_is_platform_admin BOOLEAN DEFAULT NULL                                              
  ) RETURNS VOID
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = public
  AS $$
  BEGIN
    UPDATE profiles SET
      full_name = COALESCE(p_full_name, full_name),
      is_platform_admin = COALESCE(p_is_platform_admin, is_platform_admin),
      updated_at = NOW()
    WHERE id = p_user_id;

    IF p_status IS NOT NULL THEN
      EXECUTE format('UPDATE profiles SET status = %L WHERE id = %L', p_status,
  p_user_id);
    END IF;
  END;
  $$;

CREATE OR REPLACE FUNCTION protect_sensitive_columns()                                  
  RETURNS TRIGGER AS $$                                                                   
  BEGIN                                                                                   
      IF (NEW.is_platform_admin IS DISTINCT FROM OLD.is_platform_admin) THEN              
          -- Si auth.uid() es NULL → es service_role o postgres → permitir
          IF auth.uid() IS NULL THEN
              RETURN NEW;
          END IF;
          -- Para usuarios autenticados, verificar que sea admin
          IF NOT COALESCE((SELECT is_platform_admin FROM public.profiles WHERE id =
  auth.uid()), FALSE) THEN
              NEW.is_platform_admin := OLD.is_platform_admin;
          END IF;
      END IF;
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;


  CREATE OR REPLACE FUNCTION prevent_admin_escalation()                                   
  RETURNS TRIGGER AS $$                                                                   
  BEGIN                                                                                   
      IF (NEW.is_platform_admin IS DISTINCT FROM OLD.is_platform_admin) THEN              
          -- Si auth.uid() es NULL → es service_role o postgres → permitir                
          IF auth.uid() IS NULL THEN                                                      
              RETURN NEW;                                                                 
          END IF;                                                                         
          -- Para usuarios autenticados, verificar que sea admin                          
          IF NOT COALESCE((SELECT is_platform_admin FROM public.profiles WHERE id =       
  auth.uid()), FALSE) THEN                                                                
              NEW.is_platform_admin := OLD.is_platform_admin;                             
          END IF;                                                                         
      END IF;                                                                             
      RETURN NEW;                                                                         
  END;                                                                                    
  $$ LANGUAGE plpgsql;     