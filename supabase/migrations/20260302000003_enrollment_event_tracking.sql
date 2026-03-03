-- Migration: Add event_id to enrollments for traceability
-- Records which event triggered each enrollment (nullable: existing enrollments had no event)

ALTER TABLE journeys.enrollments
    ADD COLUMN event_id UUID REFERENCES crm.org_events(id) ON DELETE SET NULL;
