-- =============================================================================
-- MIGRATION: Initial Schema - Core Tables for Multi-Tenant Auth
-- =============================================================================
-- This migration creates the foundational tables for the OASIS platform:
-- 1. ENUMs for type safety
-- 2. profiles - User profiles (synced with auth.users)
-- 3. organizations - Multi-tenant organizations
-- 4. organization_members - User-Org relationships with roles
-- 5. Triggers for automatic profile creation
-- =============================================================================

-- =============================================================================
-- 1. EXTENSIONS
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- 2. ENUMS - Type-safe values for roles and statuses
-- =============================================================================

-- Organization types
DO $$ BEGIN
    CREATE TYPE org_type AS ENUM ('community', 'provider', 'sponsor', 'enterprise');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Organization member roles (hierarchical)
DO $$ BEGIN
    CREATE TYPE member_role AS ENUM ('owner', 'admin', 'facilitador', 'participante');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Membership status
DO $$ BEGIN
    CREATE TYPE membership_status AS ENUM ('active', 'invited', 'suspended', 'inactive');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- User account status (global)
DO $$ BEGIN
    CREATE TYPE account_status AS ENUM ('active', 'suspended', 'pending_verification', 'deleted');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- =============================================================================
-- 3. PROFILES TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    -- Primary key matches auth.users.id
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Basic info
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,

    -- Platform-level permissions
    is_platform_admin BOOLEAN DEFAULT FALSE NOT NULL,

    -- Account status (global, not per-org)
    status account_status DEFAULT 'active' NOT NULL,

    -- Flexible metadata (preferences, settings, etc.)
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_profiles_updated_at ON public.profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- =============================================================================
-- 4. ORGANIZATIONS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    logo_url TEXT,

    -- Classification
    type org_type DEFAULT 'provider' NOT NULL,

    -- Flexible settings (features, theme, limits, etc.)
    settings JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

DROP TRIGGER IF EXISTS update_organizations_updated_at ON public.organizations;
CREATE TRIGGER update_organizations_updated_at
    BEFORE UPDATE ON public.organizations
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- =============================================================================
-- 5. ORGANIZATION MEMBERS TABLE (Junction with roles)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationships
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,

    -- Role and status within this organization
    role member_role DEFAULT 'participante' NOT NULL,
    status membership_status DEFAULT 'active' NOT NULL,

    -- Membership metadata
    invited_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    invited_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint: one membership per user per org
    CONSTRAINT unique_org_member UNIQUE (organization_id, user_id)
);

-- =============================================================================
-- 6. DEFAULT COMMUNITY ORGANIZATION
-- =============================================================================
-- This is the "catch-all" organization for users without explicit membership
-- UUID is auto-generated, referenced by slug in trigger
INSERT INTO public.organizations (name, slug, type, description, settings)
VALUES (
    'OASIS Community',
    'oasis-community',
    'community',
    'Comunidad abierta de OASIS. Todos los usuarios son miembros por defecto.',
    '{"is_default": true, "features": ["public_content"]}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- =============================================================================
-- 7. TRIGGER: Auto-create profile on user signup
-- =============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    community_org_id UUID;
BEGIN
    -- Create profile from auth.users data
    INSERT INTO public.profiles (id, email, full_name, avatar_url, metadata)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.raw_user_meta_data->>'avatar_url',
        COALESCE(NEW.raw_user_meta_data, '{}'::jsonb)
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        updated_at = NOW();

    -- Lookup default community organization by slug (no hardcoded UUIDs)
    SELECT id INTO community_org_id
    FROM public.organizations
    WHERE slug = 'oasis-community'
    LIMIT 1;

    -- Auto-assign to community organization if it exists
    IF community_org_id IS NOT NULL THEN
        INSERT INTO public.organization_members (organization_id, user_id, role, status)
        VALUES (community_org_id, NEW.id, 'participante', 'active')
        ON CONFLICT (organization_id, user_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Drop existing trigger if exists and recreate
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- =============================================================================
-- 8. HELPER FUNCTIONS FOR RLS
-- =============================================================================

-- Check if current user is platform admin
CREATE OR REPLACE FUNCTION public.get_is_platform_admin()
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT COALESCE(
        (SELECT is_platform_admin FROM public.profiles WHERE id = auth.uid()),
        FALSE
    );
$$;

-- Get organization IDs where current user is an active member
CREATE OR REPLACE FUNCTION public.get_my_org_ids()
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
CREATE OR REPLACE FUNCTION public.get_my_role_in_org(org_id UUID)
RETURNS member_role
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT role
    FROM public.organization_members
    WHERE user_id = auth.uid()
    AND organization_id = org_id
    AND status = 'active'
    LIMIT 1;
$$;

-- =============================================================================
-- 9. ENABLE RLS (Policies defined in separate migration)
-- =============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- 10. INDEXES FOR PERFORMANCE
-- =============================================================================

-- Profiles
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_status ON public.profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_platform_admin ON public.profiles(is_platform_admin) WHERE is_platform_admin = TRUE;

-- Organizations
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON public.organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_type ON public.organizations(type);

-- Organization Members
CREATE INDEX IF NOT EXISTS idx_org_members_user_id ON public.organization_members(user_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org_id ON public.organization_members(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user_org ON public.organization_members(user_id, organization_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org_role ON public.organization_members(organization_id, role) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_org_members_active ON public.organization_members(user_id, status) WHERE status = 'active';

-- =============================================================================
-- DONE
-- =============================================================================
COMMENT ON TABLE public.profiles IS 'User profiles synced with auth.users';
COMMENT ON TABLE public.organizations IS 'Multi-tenant organizations';
COMMENT ON TABLE public.organization_members IS 'User membership and roles per organization';
