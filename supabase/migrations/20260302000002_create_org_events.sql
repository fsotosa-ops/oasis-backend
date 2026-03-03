-- Migration: Create org_events table
-- Implements the "QR Eterno" principle: permanent URLs per org+event slug pair

CREATE TYPE event_status AS ENUM ('upcoming', 'live', 'past', 'cancelled');

CREATE TABLE IF NOT EXISTS public.org_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    journey_id      UUID REFERENCES journeys.journeys(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    description     TEXT,
    start_date      TIMESTAMPTZ,
    end_date        TIMESTAMPTZ,
    location        TEXT,
    status          event_status NOT NULL DEFAULT 'upcoming',
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
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER org_events_updated_at
    BEFORE UPDATE ON public.org_events
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Enable RLS
ALTER TABLE public.org_events ENABLE ROW LEVEL SECURITY;

-- Public can read active events (needed for QR landing + projection screen, no auth required)
CREATE POLICY "events_public_read" ON public.org_events
    FOR SELECT
    USING (is_active = TRUE);

-- Org owners/admins can manage events
CREATE POLICY "events_admin_write" ON public.org_events
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members om
            WHERE om.organization_id = org_events.organization_id
              AND om.user_id = auth.uid()
              AND om.role IN ('owner', 'admin')
        )
    );
