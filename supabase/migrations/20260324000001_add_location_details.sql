ALTER TABLE crm.org_events
  ADD COLUMN IF NOT EXISTS location_details JSONB NOT NULL DEFAULT '{}'::jsonb;
