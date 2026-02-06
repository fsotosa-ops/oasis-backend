-- =============================================================================
-- MIGRATION: Journey Organizations (Multi-org assignment)
-- =============================================================================
-- Permite asignar un journey a multiples organizaciones via tabla pivote.
-- El journey conserva su organization_id original (owner).
-- =============================================================================

-- =============================================================================
-- 1. PIVOT TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS journeys.journey_organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journey_id UUID NOT NULL REFERENCES journeys.journeys(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,

    CONSTRAINT uq_journey_organization UNIQUE (journey_id, organization_id)
);

-- =============================================================================
-- 2. INDEXES
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_journey_orgs_journey ON journeys.journey_organizations(journey_id);
CREATE INDEX IF NOT EXISTS idx_journey_orgs_org ON journeys.journey_organizations(organization_id);

-- =============================================================================
-- 3. RLS
-- =============================================================================
ALTER TABLE journeys.journey_organizations ENABLE ROW LEVEL SECURITY;

-- SELECT: Members of the org can see assignments for their org
DROP POLICY IF EXISTS "read_journey_organizations" ON journeys.journey_organizations;
CREATE POLICY "read_journey_organizations" ON journeys.journey_organizations
    FOR SELECT USING (
        organization_id IN (SELECT public.get_user_org_ids())
        OR public.is_platform_admin() = TRUE
    );

-- ALL: Platform admins can manage assignments
DROP POLICY IF EXISTS "admin_journey_organizations" ON journeys.journey_organizations;
CREATE POLICY "admin_journey_organizations" ON journeys.journey_organizations
    FOR ALL USING (public.is_platform_admin() = TRUE);

-- =============================================================================
-- 4. GRANTS
-- =============================================================================
GRANT SELECT ON TABLE journeys.journey_organizations TO authenticated;
GRANT INSERT, UPDATE, DELETE ON TABLE journeys.journey_organizations TO authenticated;

-- =============================================================================
-- 5. UPDATE read_journeys POLICY
-- =============================================================================
-- Include journeys assigned via junction table
DROP POLICY IF EXISTS "read_journeys" ON journeys.journeys;
CREATE POLICY "read_journeys" ON journeys.journeys FOR SELECT USING (
    is_active = true
    OR (EXISTS (SELECT 1 FROM journeys.enrollments WHERE journey_id = id AND user_id = auth.uid()))
    OR (EXISTS (
        SELECT 1 FROM journeys.journey_organizations jo
        WHERE jo.journey_id = id
        AND jo.organization_id IN (SELECT public.get_user_org_ids())
    ))
    OR public.is_admin_secure()
);

-- =============================================================================
-- 6. BACKFILL: Insert existing journeys into junction table
-- =============================================================================
INSERT INTO journeys.journey_organizations (journey_id, organization_id, assigned_at)
SELECT id, organization_id, created_at
FROM journeys.journeys
ON CONFLICT (journey_id, organization_id) DO NOTHING;

-- =============================================================================
SELECT 'journey_organizations pivot table created and backfilled' AS status;
