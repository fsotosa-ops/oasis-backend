-- Migration: Add is_onboarding flag to journeys and profile_question step type
-- This enables:
-- 1. Marking a journey as "onboarding" directly (is_onboarding boolean)
-- 2. A new step type "profile_question" for CRM profile fields within journeys

-- 1. Add is_onboarding flag to journeys table
ALTER TABLE journeys.journeys
  ADD COLUMN IF NOT EXISTS is_onboarding boolean NOT NULL DEFAULT false;

-- Only one journey per organization can be the onboarding journey.
-- A partial unique index enforces this constraint.
CREATE UNIQUE INDEX IF NOT EXISTS uq_journeys_one_onboarding_per_org
  ON journeys.journeys (organization_id)
  WHERE is_onboarding = true;

-- 2. Drop and recreate the step type enum to add 'profile_question'
-- PostgreSQL doesn't allow IF NOT EXISTS on ALTER TYPE ADD VALUE in all versions,
-- so we use a safe DO block.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_enum
    WHERE enumlabel = 'profile_question'
      AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'step_type')
  ) THEN
    ALTER TYPE journeys.step_type ADD VALUE 'profile_question';
  END IF;
EXCEPTION
  WHEN others THEN
    -- step_type might not be an enum (could be text); in that case, nothing to do
    NULL;
END $$;

-- 3. When a journey is marked as onboarding, automatically sync the
--    gamification_config.profile_completion_journey_id for backward compatibility.
CREATE OR REPLACE FUNCTION journeys.sync_onboarding_journey_config()
RETURNS trigger AS $$
BEGIN
  IF NEW.is_onboarding = true THEN
    INSERT INTO journeys.gamification_config (organization_id, profile_completion_journey_id)
    VALUES (NEW.organization_id, NEW.id)
    ON CONFLICT (organization_id)
    DO UPDATE SET profile_completion_journey_id = NEW.id;
  ELSIF OLD.is_onboarding = true AND NEW.is_onboarding = false THEN
    UPDATE journeys.gamification_config
    SET profile_completion_journey_id = NULL
    WHERE organization_id = NEW.organization_id
      AND profile_completion_journey_id = NEW.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_sync_onboarding_journey ON journeys.journeys;
CREATE TRIGGER trg_sync_onboarding_journey
  AFTER INSERT OR UPDATE OF is_onboarding ON journeys.journeys
  FOR EACH ROW
  EXECUTE FUNCTION journeys.sync_onboarding_journey_config();
