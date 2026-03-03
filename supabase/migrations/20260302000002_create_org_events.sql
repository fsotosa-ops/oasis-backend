-- Migration: Create org_events table in crm schema
-- Implements the "QR Eterno" principle: permanent URLs per org+event slug pair
-- Uses TEXT + CHECK instead of ENUM (avoids ALTER TYPE issues like with org_type)

CREATE TABLE IF NOT EXISTS crm.org_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    journey_id      UUID REFERENCES journeys.journeys(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    description     TEXT,
    start_date      TIMESTAMPTZ,
    end_date        TIMESTAMPTZ,
    location        TEXT,
    status          TEXT NOT NULL DEFAULT 'upcoming'
                    CHECK (status IN ('upcoming', 'live', 'past', 'cancelled')),
    landing_config  JSONB NOT NULL DEFAULT '{
        "title": null,
        "welcome_message": null,
        "primary_color": "#3B82F6",
        "background_color": "#0F172A",
        "show_qr": true,
        "custom_logo_url": null
    }'::jsonb,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_event_slug_per_org UNIQUE (organization_id, slug)
);

-- Auto-update updated_at on any change
DROP TRIGGER IF EXISTS crm_org_events_updated_at ON crm.org_events;
CREATE TRIGGER crm_org_events_updated_at
    BEFORE UPDATE ON crm.org_events
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Enable RLS
ALTER TABLE crm.org_events ENABLE ROW LEVEL SECURITY;

-- Public can read active events (needed for QR landing + projection screen, no auth required)
DROP POLICY IF EXISTS "events_public_read" ON crm.org_events;
CREATE POLICY "events_public_read" ON crm.org_events
    FOR SELECT
    USING (is_active = TRUE);

-- Org owners/admins can manage events
DROP POLICY IF EXISTS "events_admin_write" ON crm.org_events;
CREATE POLICY "events_admin_write" ON crm.org_events
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members om
            WHERE om.organization_id = crm.org_events.organization_id
              AND om.user_id = auth.uid()
              AND om.role IN ('owner', 'admin')
        )
    );

-- Grants
GRANT ALL ON crm.org_events TO service_role;
GRANT SELECT ON crm.org_events TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON crm.org_events TO authenticated;
