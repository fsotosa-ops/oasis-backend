-- =============================================================================
-- MIGRATION: Resource Schema
-- =============================================================================
-- Creates a dedicated `resources` schema for managing educational content
-- (videos, podcasts, PDFs, capsulas, actividades) with unlock conditions
-- based on gamification (points, levels, rewards, journey completion).
-- =============================================================================

-- =============================================================================
-- 1. SCHEMA
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS resources;
GRANT USAGE ON SCHEMA resources TO authenticated, service_role, anon;

-- =============================================================================
-- 2. TABLES
-- =============================================================================

-- Main resources table
CREATE TABLE resources.resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('video', 'podcast', 'pdf', 'capsula', 'actividad')),
    content_url TEXT,
    storage_path TEXT,
    thumbnail_url TEXT,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    points_on_completion INT NOT NULL DEFAULT 0,
    unlock_logic TEXT NOT NULL DEFAULT 'AND' CHECK (unlock_logic IN ('AND', 'OR')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Multi-org assignment (mirrors journeys.journey_organizations)
CREATE TABLE resources.resource_organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID NOT NULL REFERENCES resources.resources(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,

    CONSTRAINT uq_resource_organization UNIQUE (resource_id, organization_id)
);

-- Unlock conditions
CREATE TABLE resources.resource_unlock_conditions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID NOT NULL REFERENCES resources.resources(id) ON DELETE CASCADE,
    condition_type TEXT NOT NULL CHECK (condition_type IN ('points_threshold', 'level_required', 'reward_required', 'journey_completed')),
    reference_id UUID,
    reference_value INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Consumption tracking
CREATE TABLE resources.resource_consumptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID NOT NULL REFERENCES resources.resources(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    time_on_page_seconds INT DEFAULT 0,
    points_awarded INT DEFAULT 0,

    CONSTRAINT uq_resource_consumption UNIQUE (resource_id, user_id)
);

-- =============================================================================
-- 3. INDEXES
-- =============================================================================
CREATE INDEX idx_resources_org ON resources.resources(organization_id);
CREATE INDEX idx_resources_type ON resources.resources(type);
CREATE INDEX idx_resources_published ON resources.resources(is_published);

CREATE INDEX idx_resource_orgs_resource ON resources.resource_organizations(resource_id);
CREATE INDEX idx_resource_orgs_org ON resources.resource_organizations(organization_id);

CREATE INDEX idx_resource_conditions_resource ON resources.resource_unlock_conditions(resource_id);

CREATE INDEX idx_resource_consumptions_user ON resources.resource_consumptions(user_id);
CREATE INDEX idx_resource_consumptions_resource ON resources.resource_consumptions(resource_id);

-- =============================================================================
-- 4. updated_at TRIGGER
-- =============================================================================
CREATE OR REPLACE FUNCTION resources.update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_resources_updated_at
    BEFORE UPDATE ON resources.resources
    FOR EACH ROW
    EXECUTE FUNCTION resources.update_updated_at();

-- =============================================================================
-- 5. RLS POLICIES
-- =============================================================================

-- --- resources.resources ---
ALTER TABLE resources.resources ENABLE ROW LEVEL SECURITY;

-- SELECT: published + assigned to user's orgs, or admin
CREATE POLICY "read_resources" ON resources.resources
    FOR SELECT USING (
        (
            is_published = true
            AND (
                organization_id IN (SELECT public.get_user_org_ids())
                OR EXISTS (
                    SELECT 1 FROM resources.resource_organizations ro
                    WHERE ro.resource_id = id
                    AND ro.organization_id IN (SELECT public.get_user_org_ids())
                )
            )
        )
        OR public.is_admin_secure()
    );

-- ALL: platform admin full access
CREATE POLICY "admin_resources" ON resources.resources
    FOR ALL USING (public.is_platform_admin() = TRUE);

-- INSERT/UPDATE/DELETE for org admins on their own org resources
CREATE POLICY "org_admin_resources" ON resources.resources
    FOR ALL USING (
        public.is_org_admin(organization_id) = TRUE
    );

-- --- resources.resource_organizations ---
ALTER TABLE resources.resource_organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "read_resource_organizations" ON resources.resource_organizations
    FOR SELECT USING (
        organization_id IN (SELECT public.get_user_org_ids())
        OR public.is_platform_admin() = TRUE
    );

CREATE POLICY "admin_resource_organizations" ON resources.resource_organizations
    FOR ALL USING (public.is_platform_admin() = TRUE);

-- --- resources.resource_unlock_conditions ---
ALTER TABLE resources.resource_unlock_conditions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "read_resource_conditions" ON resources.resource_unlock_conditions
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM resources.resources r
            WHERE r.id = resource_id
            AND (
                r.organization_id IN (SELECT public.get_user_org_ids())
                OR public.is_admin_secure()
            )
        )
    );

CREATE POLICY "admin_resource_conditions" ON resources.resource_unlock_conditions
    FOR ALL USING (public.is_platform_admin() = TRUE);

CREATE POLICY "org_admin_resource_conditions" ON resources.resource_unlock_conditions
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM resources.resources r
            WHERE r.id = resource_id
            AND public.is_org_admin(r.organization_id) = TRUE
        )
    );

-- --- resources.resource_consumptions ---
ALTER TABLE resources.resource_consumptions ENABLE ROW LEVEL SECURITY;

-- Users can read/write their own consumption data
CREATE POLICY "own_consumptions" ON resources.resource_consumptions
    FOR ALL USING (user_id = auth.uid());

-- Admins can read all consumptions
CREATE POLICY "admin_read_consumptions" ON resources.resource_consumptions
    FOR SELECT USING (public.is_admin_secure());

-- =============================================================================
-- 6. GRANTS
-- =============================================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA resources TO service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA resources TO authenticated;
GRANT INSERT, UPDATE ON resources.resource_consumptions TO authenticated;

-- =============================================================================
SELECT 'resources schema created successfully' AS status;
