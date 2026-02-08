-- Add missing updated_at column to enrollments table
-- Required by the handle_step_completion() trigger which does SET updated_at = now()
ALTER TABLE journeys.enrollments
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
