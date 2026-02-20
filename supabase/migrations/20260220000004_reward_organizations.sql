-- =============================================================================
-- MIGRATION: Reward Organizations (Multi-org assignment)
-- =============================================================================
-- Permite asignar una recompensa a múltiples organizaciones via tabla pivote.
-- La recompensa conserva su organization_id original (owner/creador).
-- =============================================================================

-- 1. PIVOT TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS journeys.reward_organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reward_id       UUID NOT NULL REFERENCES journeys.rewards_catalog(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by     UUID REFERENCES public.profiles(id) ON DELETE SET NULL,

    CONSTRAINT uq_reward_organization UNIQUE (reward_id, organization_id)
);

-- 2. INDEXES
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_reward_orgs_reward ON journeys.reward_organizations(reward_id);
CREATE INDEX IF NOT EXISTS idx_reward_orgs_org    ON journeys.reward_organizations(organization_id);

-- 3. RLS
-- =============================================================================
ALTER TABLE journeys.reward_organizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "read_reward_organizations" ON journeys.reward_organizations;
CREATE POLICY "read_reward_organizations" ON journeys.reward_organizations
    FOR SELECT USING (
        organization_id IN (SELECT public.get_user_org_ids())
        OR public.is_platform_admin() = TRUE
    );

DROP POLICY IF EXISTS "admin_reward_organizations" ON journeys.reward_organizations;
CREATE POLICY "admin_reward_organizations" ON journeys.reward_organizations
    FOR ALL USING (public.is_platform_admin() = TRUE);

-- 4. GRANTS
-- =============================================================================
GRANT SELECT ON TABLE journeys.reward_organizations TO authenticated;
GRANT INSERT, UPDATE, DELETE ON TABLE journeys.reward_organizations TO authenticated;

-- 5. BACKFILL: registrar la org propietaria de cada reward existente
-- =============================================================================
INSERT INTO journeys.reward_organizations (reward_id, organization_id, assigned_at)
SELECT id, organization_id, NOW()
FROM journeys.rewards_catalog
WHERE organization_id IS NOT NULL
ON CONFLICT (reward_id, organization_id) DO NOTHING;

SELECT 'reward_organizations pivot table created and backfilled' AS status;
