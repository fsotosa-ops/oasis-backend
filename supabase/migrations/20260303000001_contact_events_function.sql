-- Migration: RPC function to get events a contact participated in
-- Cross-schema query: journeys.enrollments + public.org_events + public.organizations

CREATE OR REPLACE FUNCTION public.get_contact_events(p_user_id UUID)
RETURNS TABLE (
    enrollment_id   TEXT,
    enrollment_status TEXT,
    enrolled_at     TIMESTAMPTZ,
    event_id        TEXT,
    event_name      TEXT,
    event_slug      TEXT,
    event_status    TEXT,
    event_start_date TIMESTAMPTZ,
    event_location  TEXT,
    org_id          TEXT,
    org_name        TEXT,
    org_slug        TEXT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT
        e.id::text       AS enrollment_id,
        e.status::text   AS enrollment_status,
        e.started_at     AS enrolled_at,
        oe.id::text      AS event_id,
        oe.name          AS event_name,
        oe.slug          AS event_slug,
        oe.status::text  AS event_status,
        oe.start_date    AS event_start_date,
        oe.location      AS event_location,
        o.id::text       AS org_id,
        o.name           AS org_name,
        o.slug           AS org_slug
    FROM journeys.enrollments e
    JOIN public.org_events oe ON e.event_id = oe.id
    JOIN public.organizations o ON oe.organization_id = o.id
    WHERE e.user_id = p_user_id
      AND e.event_id IS NOT NULL
    ORDER BY e.started_at DESC;
$$;
