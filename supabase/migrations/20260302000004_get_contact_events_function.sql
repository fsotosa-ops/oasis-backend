-- Migration: Create get_contact_events function
-- Called by backend via db.rpc("get_contact_events", {"p_user_id": user_id})
-- Returns all events a contact has attended (via enrollment event_id)

CREATE OR REPLACE FUNCTION public.get_contact_events(p_user_id UUID)
RETURNS TABLE (
    enrollment_id     TEXT,
    enrollment_status TEXT,
    enrolled_at       TIMESTAMPTZ,
    event_id          TEXT,
    event_name        TEXT,
    event_slug        TEXT,
    event_status      TEXT,
    event_start_date  TIMESTAMPTZ,
    event_location    TEXT,
    org_id            TEXT,
    org_name          TEXT,
    org_slug          TEXT
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, crm, journeys
AS $$
    SELECT
        e.id::TEXT,
        e.status,
        e.started_at,
        oe.id::TEXT,
        oe.name,
        oe.slug,
        oe.status,
        oe.start_date,
        oe.location,
        o.id::TEXT,
        o.name,
        o.slug
    FROM journeys.enrollments e
    JOIN crm.org_events oe ON e.event_id = oe.id
    JOIN public.organizations o ON oe.organization_id = o.id
    WHERE e.user_id = p_user_id
      AND e.event_id IS NOT NULL
    ORDER BY e.started_at DESC;
$$;
