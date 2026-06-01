-- Add scheduling fields to steps for date/time-based release control
ALTER TABLE journeys.steps
  ADD COLUMN IF NOT EXISTS available_from TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS unlock_hours_after_start INTEGER DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS unlock_hours_after_previous INTEGER DEFAULT NULL;

-- Add scheduling to journeys for controlling when a journey opens for enrollment
ALTER TABLE journeys.journeys
  ADD COLUMN IF NOT EXISTS available_from TIMESTAMPTZ DEFAULT NULL;
