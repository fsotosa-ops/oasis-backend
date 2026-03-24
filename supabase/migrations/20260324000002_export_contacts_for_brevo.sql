-- Migration: Create RPC function to export contacts as a flat table for Brevo CSV
-- Follows SECURITY DEFINER pattern from get_contact_events
-- Supports filtering by multiple organizations and/or created_at date range

DROP FUNCTION IF EXISTS public.export_contacts_for_brevo(UUID);

CREATE OR REPLACE FUNCTION public.export_contacts_for_brevo(
    p_organization_ids UUID[] DEFAULT NULL,
    p_created_from     TIMESTAMPTZ DEFAULT NULL,
    p_created_to       TIMESTAMPTZ DEFAULT NULL
)
RETURNS TABLE (
    user_id          TEXT,
    email            TEXT,
    first_name       TEXT,
    last_name        TEXT,
    phone            TEXT,
    company          TEXT,
    country          TEXT,
    state            TEXT,
    city             TEXT,
    birth_date       TEXT,
    gender           TEXT,
    education_level  TEXT,
    occupation       TEXT,
    crm_status       TEXT,
    oasis_score      INT,
    organizations    TEXT,
    total_events_attended BIGINT,
    last_event_name  TEXT,
    last_event_date  TEXT,
    total_points     BIGINT,
    current_level    TEXT,
    active_journeys  TEXT,
    pending_journeys TEXT,
    completed_journeys TEXT,
    last_seen_at     TEXT,
    created_at       TEXT
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, crm, journeys
AS $$
    WITH contact_base AS (
        SELECT c.*
        FROM crm.contacts c
        WHERE (
            p_organization_ids IS NULL
            OR EXISTS (
                SELECT 1 FROM public.organization_members om
                WHERE om.user_id = c.user_id
                  AND om.organization_id = ANY(p_organization_ids)
                  AND om.status = 'active'
            )
        )
        AND (p_created_from IS NULL OR c.created_at >= p_created_from)
        AND (p_created_to   IS NULL OR c.created_at <= p_created_to)
    ),
    contact_orgs AS (
        SELECT
            om.user_id,
            STRING_AGG(
                o.name || ' (' || om.role || ')',
                ', ' ORDER BY o.name
            ) AS organizations
        FROM public.organization_members om
        JOIN public.organizations o ON o.id = om.organization_id
        WHERE om.status = 'active'
          AND om.user_id IN (SELECT cb.user_id FROM contact_base cb)
        GROUP BY om.user_id
    ),
    contact_events AS (
        SELECT
            ea.user_id,
            COUNT(*) FILTER (WHERE ea.status = 'attended') AS total_attended,
            (
                SELECT oe2.name
                FROM crm.event_attendances ea2
                JOIN crm.org_events oe2 ON oe2.id = ea2.event_id
                WHERE ea2.user_id = ea.user_id AND ea2.status = 'attended'
                ORDER BY oe2.start_date DESC NULLS LAST
                LIMIT 1
            ) AS last_event_name,
            (
                SELECT TO_CHAR(oe2.start_date AT TIME ZONE 'UTC', 'YYYY-MM-DD')
                FROM crm.event_attendances ea2
                JOIN crm.org_events oe2 ON oe2.id = ea2.event_id
                WHERE ea2.user_id = ea.user_id AND ea2.status = 'attended'
                ORDER BY oe2.start_date DESC NULLS LAST
                LIMIT 1
            ) AS last_event_date
        FROM crm.event_attendances ea
        WHERE ea.user_id IN (SELECT cb.user_id FROM contact_base cb)
        GROUP BY ea.user_id
    ),
    contact_points AS (
        SELECT
            pl.user_id,
            SUM(pl.amount) AS total_points
        FROM journeys.points_ledger pl
        WHERE pl.user_id IN (SELECT cb.user_id FROM contact_base cb)
        GROUP BY pl.user_id
    ),
    contact_levels AS (
        SELECT DISTINCT ON (cp.user_id)
            cp.user_id,
            l.name AS level_name
        FROM contact_points cp
        JOIN journeys.levels l ON cp.total_points >= l.min_points
        WHERE l.organization_id IS NULL
           OR (p_organization_ids IS NOT NULL AND l.organization_id = ANY(p_organization_ids))
        ORDER BY cp.user_id, l.min_points DESC
    ),
    contact_active_journeys AS (
        SELECT
            en.user_id,
            STRING_AGG(
                j.title || ' (' || COALESCE(ROUND(en.progress_percentage)::TEXT, '0') || '%)',
                ', ' ORDER BY j.title
            ) AS active_journeys
        FROM journeys.enrollments en
        JOIN journeys.journeys j ON j.id = en.journey_id
        WHERE en.status = 'active'
          AND en.user_id IN (SELECT cb.user_id FROM contact_base cb)
        GROUP BY en.user_id
    ),
    contact_pending_journeys AS (
        SELECT
            en.user_id,
            STRING_AGG(
                j.title || ' (' || en.status || ')',
                ', ' ORDER BY j.title
            ) AS pending_journeys
        FROM journeys.enrollments en
        JOIN journeys.journeys j ON j.id = en.journey_id
        WHERE en.status IN ('pending', 'dropped')
          AND en.user_id IN (SELECT cb.user_id FROM contact_base cb)
        GROUP BY en.user_id
    ),
    contact_completed_journeys AS (
        SELECT
            en.user_id,
            STRING_AGG(j.title, ', ' ORDER BY j.title) AS completed_journeys
        FROM journeys.enrollments en
        JOIN journeys.journeys j ON j.id = en.journey_id
        WHERE en.status = 'completed'
          AND en.user_id IN (SELECT cb.user_id FROM contact_base cb)
        GROUP BY en.user_id
    )
    SELECT
        cb.user_id::TEXT,
        cb.email,
        cb.first_name,
        cb.last_name,
        cb.phone,
        cb.company,
        cb.country,
        cb.state,
        cb.city,
        TO_CHAR(cb.birth_date, 'YYYY-MM-DD'),
        cb.gender,
        cb.education_level,
        cb.occupation,
        cb.status,
        0 AS oasis_score,
        co.organizations,
        COALESCE(ce.total_attended, 0),
        ce.last_event_name,
        ce.last_event_date,
        COALESCE(cp.total_points, 0),
        cl.level_name,
        caj.active_journeys,
        cpj.pending_journeys,
        ccj.completed_journeys,
        TO_CHAR(cb.last_seen_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
        TO_CHAR(cb.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    FROM contact_base cb
    LEFT JOIN contact_orgs co ON co.user_id = cb.user_id
    LEFT JOIN contact_events ce ON ce.user_id = cb.user_id
    LEFT JOIN contact_points cp ON cp.user_id = cb.user_id
    LEFT JOIN contact_levels cl ON cl.user_id = cb.user_id
    LEFT JOIN contact_active_journeys caj ON caj.user_id = cb.user_id
    LEFT JOIN contact_pending_journeys cpj ON cpj.user_id = cb.user_id
    LEFT JOIN contact_completed_journeys ccj ON ccj.user_id = cb.user_id
    ORDER BY cb.created_at DESC;
$$;
