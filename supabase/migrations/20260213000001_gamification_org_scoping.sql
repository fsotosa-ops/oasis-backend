-- =============================================================================
-- MIGRATION: Gamification Org-Scoping
-- =============================================================================
-- Adds organization_id to points_ledger and user_activities so gamification
-- data can be filtered per-org. Creates gamification_config table for
-- per-org settings. Updates handle_step_completion() trigger to populate
-- organization_id and respect org config.
-- =============================================================================

-- =============================================================================
-- 1. ADD organization_id TO points_ledger & user_activities
-- =============================================================================

ALTER TABLE journeys.points_ledger
ADD COLUMN organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;

ALTER TABLE journeys.user_activities
ADD COLUMN organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;

-- Indexes for org-scoped queries
CREATE INDEX idx_ledger_org ON journeys.points_ledger(organization_id);
CREATE INDEX idx_activities_org ON journeys.user_activities(organization_id);

-- =============================================================================
-- 2. BACKFILL existing data from step_completions → journeys
-- =============================================================================

-- Backfill points_ledger: reference_id points to step_completions.id
UPDATE journeys.points_ledger pl
SET organization_id = j.organization_id
FROM journeys.step_completions sc
JOIN journeys.journeys j ON j.id = sc.journey_id
WHERE pl.reference_id = sc.id
  AND pl.organization_id IS NULL;

-- Backfill user_activities: metadata->>'step_id' → steps → journeys
UPDATE journeys.user_activities ua
SET organization_id = j.organization_id
FROM journeys.steps s
JOIN journeys.journeys j ON j.id = s.journey_id
WHERE ua.metadata->>'step_id' = s.id::TEXT
  AND ua.organization_id IS NULL;

-- =============================================================================
-- 3. CREATE gamification_config TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS journeys.gamification_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL UNIQUE REFERENCES public.organizations(id) ON DELETE CASCADE,

    -- Feature toggles
    points_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    levels_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rewards_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    -- Points multiplier (e.g. 1.5 = 50% bonus on all points)
    points_multiplier NUMERIC(4,2) NOT NULL DEFAULT 1.00,

    -- Default points when step has no gamification_rules
    default_step_points INTEGER NOT NULL DEFAULT 10,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE journeys.gamification_config ENABLE ROW LEVEL SECURITY;

-- Admins of the org can view config
CREATE POLICY "Config: Org admins can view"
ON journeys.gamification_config
FOR SELECT USING (
    organization_id IN (SELECT public.get_my_org_ids())
);

-- Trigger to auto-update updated_at
CREATE TRIGGER update_gamification_config_timestamp
BEFORE UPDATE ON journeys.gamification_config
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Grant service_role full access
GRANT ALL ON TABLE journeys.gamification_config TO service_role;

-- =============================================================================
-- 4. UPDATE get_user_total_points() → org-scoped version
-- =============================================================================

-- Drop the old function first (single-param signature)
DROP FUNCTION IF EXISTS journeys.get_user_total_points(UUID);

-- New org-aware version: NULL org_id = sum across all orgs (backward compat)
CREATE OR REPLACE FUNCTION journeys.get_user_total_points(uid UUID, org UUID DEFAULT NULL)
RETURNS INTEGER
LANGUAGE SQL
STABLE
SECURITY DEFINER
AS $$
    SELECT COALESCE(SUM(amount), 0)::INTEGER
    FROM journeys.points_ledger
    WHERE user_id = uid
      AND (org IS NULL OR organization_id = org);
$$;

GRANT EXECUTE ON FUNCTION journeys.get_user_total_points(UUID, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION journeys.get_user_total_points(UUID, UUID) TO service_role;

-- =============================================================================
-- 5. UPDATE get_user_current_level() to use new get_user_total_points sig
-- =============================================================================

-- Must DROP first: original returns TABLE(...), new returns JSONB
DROP FUNCTION IF EXISTS journeys.get_user_current_level(UUID, UUID);

CREATE OR REPLACE FUNCTION journeys.get_user_current_level(uid UUID, org_id UUID)
RETURNS JSONB
LANGUAGE SQL
STABLE
SECURITY DEFINER
AS $$
    WITH user_points AS (
        SELECT journeys.get_user_total_points(uid, org_id) AS total
    ),
    current_level AS (
        SELECT l.id, l.name, l.min_points
        FROM journeys.levels l, user_points up
        WHERE (l.organization_id = org_id OR l.organization_id IS NULL)
          AND l.min_points <= up.total
        ORDER BY l.min_points DESC
        LIMIT 1
    ),
    next_level AS (
        SELECT l.id, l.name, l.min_points
        FROM journeys.levels l, user_points up
        WHERE (l.organization_id = org_id OR l.organization_id IS NULL)
          AND l.min_points > up.total
        ORDER BY l.min_points ASC
        LIMIT 1
    )
    SELECT jsonb_build_object(
        'total_points', (SELECT total FROM user_points),
        'current_level', (SELECT row_to_json(current_level)::JSONB FROM current_level),
        'next_level', (SELECT row_to_json(next_level)::JSONB FROM next_level)
    );
$$;

-- =============================================================================
-- 6. UPDATE handle_step_completion() TRIGGER
-- =============================================================================

CREATE OR REPLACE FUNCTION journeys.handle_step_completion()
RETURNS TRIGGER AS $$
DECLARE
    v_points INTEGER;
    v_step_config JSONB;
    v_journey_id UUID;
    v_org_id UUID;
    v_config RECORD;
    v_reward RECORD;
    v_multiplier NUMERIC(4,2) := 1.00;
BEGIN
    -- 1. Get journey_id and resolve organization_id
    v_journey_id := NEW.journey_id;

    SELECT j.organization_id INTO v_org_id
    FROM journeys.journeys j
    WHERE j.id = v_journey_id;

    -- 2. Load org gamification config (if exists)
    SELECT * INTO v_config
    FROM journeys.gamification_config
    WHERE organization_id = v_org_id;

    -- If points are disabled for this org, skip gamification entirely
    IF v_config IS NOT NULL AND v_config.points_enabled = FALSE THEN
        NEW.points_earned := 0;
        RETURN NEW;
    END IF;

    -- 3. Determine base points from step config
    SELECT gamification_rules INTO v_step_config
    FROM journeys.steps
    WHERE id = NEW.step_id;

    IF v_step_config IS NOT NULL AND (v_step_config->>'base_points') IS NOT NULL THEN
        v_points := (v_step_config->>'base_points')::INTEGER;
    ELSIF v_config IS NOT NULL THEN
        v_points := v_config.default_step_points;
    ELSE
        v_points := 10;
    END IF;

    -- 4. Apply org multiplier
    IF v_config IS NOT NULL THEN
        v_multiplier := v_config.points_multiplier;
    END IF;
    v_points := ROUND(v_points * v_multiplier)::INTEGER;

    -- 5. Insert into points_ledger (now with organization_id)
    INSERT INTO journeys.points_ledger (user_id, amount, reason, reference_id, organization_id)
    VALUES (NEW.user_id, v_points, 'step_completed', NEW.id, v_org_id);

    -- 6. Insert into user_activities (now with organization_id)
    INSERT INTO journeys.user_activities (user_id, type, points_awarded, metadata, organization_id)
    VALUES (
        NEW.user_id,
        'step_completed',
        v_points,
        jsonb_build_object(
            'step_id', NEW.step_id,
            'enrollment_id', NEW.enrollment_id,
            'journey_id', v_journey_id
        ),
        v_org_id
    );

    -- 7. Evaluate rewards: step_completed condition
    IF v_config IS NULL OR v_config.rewards_enabled = TRUE THEN
        FOR v_reward IN
            SELECT rc.id AS reward_id
            FROM journeys.rewards_catalog rc
            WHERE rc.unlock_condition->>'type' = 'step_completed'
              AND rc.unlock_condition->>'step_id' = NEW.step_id::TEXT
              AND (rc.organization_id = v_org_id OR rc.organization_id IS NULL)
              AND NOT EXISTS (
                  SELECT 1 FROM journeys.user_rewards ur
                  WHERE ur.user_id = NEW.user_id AND ur.reward_id = rc.id
              )
        LOOP
            INSERT INTO journeys.user_rewards (user_id, reward_id, journey_id, metadata)
            VALUES (
                NEW.user_id,
                v_reward.reward_id,
                v_journey_id,
                jsonb_build_object('trigger', 'step_completed', 'step_id', NEW.step_id)
            );
        END LOOP;

        -- 8. Evaluate rewards: points_threshold condition
        FOR v_reward IN
            SELECT rc.id AS reward_id
            FROM journeys.rewards_catalog rc
            WHERE rc.unlock_condition->>'type' = 'points_threshold'
              AND (rc.unlock_condition->>'min_points')::INTEGER
                  <= journeys.get_user_total_points(NEW.user_id, v_org_id)
              AND (rc.organization_id = v_org_id OR rc.organization_id IS NULL)
              AND NOT EXISTS (
                  SELECT 1 FROM journeys.user_rewards ur
                  WHERE ur.user_id = NEW.user_id AND ur.reward_id = rc.id
              )
        LOOP
            INSERT INTO journeys.user_rewards (user_id, reward_id, journey_id, metadata)
            VALUES (
                NEW.user_id,
                v_reward.reward_id,
                v_journey_id,
                jsonb_build_object('trigger', 'points_threshold')
            );
        END LOOP;
    END IF;

    -- 9. Update enrollment
    UPDATE journeys.enrollments
    SET updated_at = now()
    WHERE id = NEW.enrollment_id;

    -- 10. Store points earned
    NEW.points_earned := v_points;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- 7. VERIFICATION
-- =============================================================================

SELECT '✅ MIGRATION: gamification_org_scoping applied' AS result;
SELECT '  - points_ledger.organization_id added' AS detail;
SELECT '  - user_activities.organization_id added' AS detail;
SELECT '  - gamification_config table created' AS detail;
SELECT '  - get_user_total_points() now org-aware' AS detail;
SELECT '  - get_user_current_level() updated' AS detail;
SELECT '  - handle_step_completion() now org-aware with config support' AS detail;
