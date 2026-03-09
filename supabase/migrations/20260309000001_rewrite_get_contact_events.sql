-- Migration: Rewrite get_contact_events to use event_attendances as primary source
-- Old version only queried enrollments (required journey assignment → empty if no journeys)
-- New version: event_attendances is the authoritative record of participation,
-- with LEFT JOIN to enrollments for journey traceability.

DROP FUNCTION IF EXISTS public.get_contact_events(UUID);

CREATE OR REPLACE FUNCTION public.get_contact_events(p_user_id UUID)
RETURNS TABLE (
    attendance_id     TEXT,
    attendance_status TEXT,
    modality          TEXT,
    registered_at     TIMESTAMPTZ,
    checked_in_at     TIMESTAMPTZ,
    event_id          TEXT,
    event_name        TEXT,
    event_slug        TEXT,
    event_status      TEXT,
    event_start_date  TIMESTAMPTZ,
    event_location    TEXT,
    org_id            TEXT,
    org_name          TEXT,
    org_slug          TEXT,
    enrollment_id     TEXT,
    enrollment_status TEXT,
    journey_id        TEXT,
    enrolled_at       TIMESTAMPTZ
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, crm, journeys
AS $$
    SELECT
        ea.id::TEXT,
        ea.status,
        ea.modality,
        ea.registered_at,
        ea.checked_in_at,
        oe.id::TEXT,
        oe.name,
        oe.slug,
        oe.status,
        oe.start_date,
        oe.location,
        o.id::TEXT,
        o.name,
        o.slug,
        e.id::TEXT,
        e.status,
        e.journey_id::TEXT,
        e.started_at
    FROM crm.event_attendances ea
    JOIN crm.org_events oe ON ea.event_id = oe.id
    JOIN public.organizations o ON oe.organization_id = o.id
    LEFT JOIN journeys.enrollments e
        ON e.user_id = ea.user_id AND e.event_id = ea.event_id
    WHERE ea.user_id = p_user_id
    ORDER BY ea.registered_at DESC;
$$;
