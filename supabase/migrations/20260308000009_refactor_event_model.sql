-- =============================================================================
-- MIGRATION: Refactor event model — replace journey_ids[] with proper tables
-- =============================================================================
-- Problems with the old model:
--   - crm.org_events.journey_ids UUID[] has no FK constraint → dangling refs possible
--   - Arrays are not indexable for joins → "events for journey X" requires seq scan
--   - No attendance tracking — no way to know who attended an event or how
--
-- New model:
--   crm.org_events            → the event itself (unchanged except drop journey_ids)
--   crm.event_journeys        → N:M junction: which journeys happen at this event
--   crm.event_attendances     → who attended and in which modality
--
-- The distinction:
--   ATTENDANCE = "User X was at event Y" (presencial/online/híbrido)
--   ENROLLMENT = "User X is doing journey Z" (learning progress)
--   enrollment.event_id = optional link: "this enrollment was triggered at event Y"
--
-- No data migration needed — no events exist yet.
-- =============================================================================

-- =============================================================================
-- 1. Drop legacy journey_ids[] column from crm.org_events
--    (no data to migrate — confirmed no events exist)
-- =============================================================================
ALTER TABLE crm.org_events DROP COLUMN IF EXISTS journey_ids;

-- =============================================================================
-- 2. Drop public.org_events if it exists (ghost table — never in migrations)
-- =============================================================================
DROP TABLE IF EXISTS public.org_events CASCADE;

-- =============================================================================
-- 3. crm.event_journeys — N:M junction: event ↔ journey
-- =============================================================================
CREATE TABLE IF NOT EXISTS crm.event_journeys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL REFERENCES crm.org_events(id) ON DELETE CASCADE,
    journey_id  UUID NOT NULL REFERENCES journeys.journeys(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_event_journey UNIQUE (event_id, journey_id)
);

CREATE INDEX IF NOT EXISTS idx_event_journeys_event_id   ON crm.event_journeys(event_id);
CREATE INDEX IF NOT EXISTS idx_event_journeys_journey_id ON crm.event_journeys(journey_id);

-- RLS
ALTER TABLE crm.event_journeys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "event_journeys_org_admin" ON crm.event_journeys;
CREATE POLICY "event_journeys_org_admin" ON crm.event_journeys
    FOR ALL
    USING (
        EXISTS (
            SELECT 1
            FROM crm.org_events e
            JOIN public.organization_members om ON om.organization_id = e.organization_id
            WHERE e.id = crm.event_journeys.event_id
              AND om.user_id = auth.uid()
              AND om.role IN ('owner', 'admin')
        )
    );

DROP POLICY IF EXISTS "event_journeys_member_read" ON crm.event_journeys;
CREATE POLICY "event_journeys_member_read" ON crm.event_journeys
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM crm.org_events e
            JOIN public.organization_members om ON om.organization_id = e.organization_id
            WHERE e.id = crm.event_journeys.event_id
              AND om.user_id = auth.uid()
        )
    );

GRANT ALL    ON crm.event_journeys TO service_role;
GRANT SELECT ON crm.event_journeys TO anon;
GRANT SELECT, INSERT, DELETE ON crm.event_journeys TO authenticated;

-- =============================================================================
-- 4. crm.event_attendances — who attended an event and how
-- =============================================================================
CREATE TABLE IF NOT EXISTS crm.event_attendances (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id      UUID NOT NULL REFERENCES crm.org_events(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,

    -- How this person attended
    modality      TEXT NOT NULL DEFAULT 'presencial'
                  CHECK (modality IN ('presencial', 'online', 'hibrido')),

    -- Lifecycle
    status        TEXT NOT NULL DEFAULT 'registered'
                  CHECK (status IN ('registered', 'attended', 'no_show', 'cancelled')),

    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checked_in_at TIMESTAMPTZ,   -- set when status → 'attended' (QR scan or manual)

    -- Optional context
    notes         TEXT,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT unique_event_attendance UNIQUE (event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_event_attendances_event_id ON crm.event_attendances(event_id);
CREATE INDEX IF NOT EXISTS idx_event_attendances_user_id  ON crm.event_attendances(user_id);

-- Auto-set checked_in_at when status changes to 'attended'
CREATE OR REPLACE FUNCTION crm.handle_attendance_check_in()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'attended' AND OLD.status != 'attended' THEN
        NEW.checked_in_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_attendance_check_in ON crm.event_attendances;
CREATE TRIGGER trg_attendance_check_in
BEFORE UPDATE ON crm.event_attendances
FOR EACH ROW EXECUTE FUNCTION crm.handle_attendance_check_in();

-- RLS
ALTER TABLE crm.event_attendances ENABLE ROW LEVEL SECURITY;

-- Org owners/admins manage all attendances for their events
DROP POLICY IF EXISTS "event_attendances_org_admin" ON crm.event_attendances;
CREATE POLICY "event_attendances_org_admin" ON crm.event_attendances
    FOR ALL
    USING (
        EXISTS (
            SELECT 1
            FROM crm.org_events e
            JOIN public.organization_members om ON om.organization_id = e.organization_id
            WHERE e.id = crm.event_attendances.event_id
              AND om.user_id = auth.uid()
              AND om.role IN ('owner', 'admin')
        )
    );

-- Users can read their own attendance records
DROP POLICY IF EXISTS "event_attendances_self_read" ON crm.event_attendances;
CREATE POLICY "event_attendances_self_read" ON crm.event_attendances
    FOR SELECT
    USING (user_id = auth.uid());

GRANT ALL    ON crm.event_attendances TO service_role;
GRANT SELECT ON crm.event_attendances TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON crm.event_attendances TO authenticated;

-- =============================================================================
-- DONE
-- =============================================================================
SELECT '✅ MIGRATION: event model refactored' AS result;
SELECT '  - journey_ids[] dropped from crm.org_events' AS detail;
SELECT '  - public.org_events dropped (was ghost table)' AS detail;
SELECT '  - crm.event_journeys created (N:M with FK)' AS detail;
SELECT '  - crm.event_attendances created (presencial/online/hibrido)' AS detail;
