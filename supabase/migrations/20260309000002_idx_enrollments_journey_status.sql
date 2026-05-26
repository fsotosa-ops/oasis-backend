-- Performance index for list_journeys_admin queries that filter by journey_id + status
CREATE INDEX IF NOT EXISTS idx_enrollments_journey_status
    ON journeys.enrollments(journey_id, status);
