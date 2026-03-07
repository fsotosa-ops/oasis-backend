-- Remove deprecated landing customization
ALTER TABLE crm.org_events DROP COLUMN IF EXISTS landing_config;

-- Add 3 new structured JSONB sections
ALTER TABLE crm.org_events
  ADD COLUMN IF NOT EXISTS counterpart_details JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS venue_details       JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS diagnosis           JSONB NOT NULL DEFAULT '{}';
