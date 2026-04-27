-- =============================================================================
-- MIGRATION: is_global flag for journeys & resources
-- =============================================================================
-- Adds an explicit "available to all organizations" flag, replacing the
-- ambiguous implicit convention (no rows in pivot table = global). When
-- is_global = TRUE the entity is visible to every authenticated user.
-- =============================================================================

ALTER TABLE journeys.journeys
    ADD COLUMN IF NOT EXISTS is_global BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE resources.resources
    ADD COLUMN IF NOT EXISTS is_global BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_journeys_is_global
    ON journeys.journeys(is_global) WHERE is_global = TRUE;

CREATE INDEX IF NOT EXISTS idx_resources_is_global
    ON resources.resources(is_global) WHERE is_global = TRUE;

-- =============================================================================
-- Update RLS: include is_global = TRUE in read policies
-- =============================================================================

-- journeys.journeys
DROP POLICY IF EXISTS "read_journeys" ON journeys.journeys;
CREATE POLICY "read_journeys" ON journeys.journeys FOR SELECT USING (
    is_active = true
    OR is_global = true
    OR (EXISTS (SELECT 1 FROM journeys.enrollments WHERE journey_id = id AND user_id = auth.uid()))
    OR (EXISTS (
        SELECT 1 FROM journeys.journey_organizations jo
        WHERE jo.journey_id = id
        AND jo.organization_id IN (SELECT public.get_user_org_ids())
    ))
    OR public.is_admin_secure()
);

-- resources.resources
DROP POLICY IF EXISTS "read_resources" ON resources.resources;
CREATE POLICY "read_resources" ON resources.resources
    FOR SELECT USING (
        (
            is_published = true
            AND (
                is_global = true
                OR organization_id IN (SELECT public.get_user_org_ids())
                OR EXISTS (
                    SELECT 1 FROM resources.resource_organizations ro
                    WHERE ro.resource_id = id
                    AND ro.organization_id IN (SELECT public.get_user_org_ids())
                )
            )
        )
        OR public.is_admin_secure()
    );

-- =============================================================================
SELECT 'is_global flag added to journeys & resources' AS status;
