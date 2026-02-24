-- =============================================================================
-- MIGRATION: Journey completion + nested-format reward evaluation
-- =============================================================================
-- Updates handle_step_completion() trigger to:
--   1. Evaluate step_completed rewards in NESTED format (conditions array)
--   2. Evaluate profile_completion rewards when step = profile_completion_step_id
--   3. Auto-complete enrollment when all steps are done
--   4. Insert journey_completed activity on completion
--   5. Award journey_completed rewards (nested format) on completion
-- =============================================================================

CREATE OR REPLACE FUNCTION journeys.handle_step_completion()
RETURNS TRIGGER AS $$
DECLARE
    v_points         INTEGER;
    v_step_config    JSONB;
    v_journey_id     UUID;
    v_org_id         UUID;
    v_config         RECORD;
    v_reward         RECORD;
    v_multiplier     NUMERIC(4,2) := 1.00;
    v_total_steps    INTEGER := 0;
    v_completed_steps INTEGER := 0;
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

    -- 5. Insert into points_ledger (with organization_id)
    INSERT INTO journeys.points_ledger (user_id, amount, reason, reference_id, organization_id)
    VALUES (NEW.user_id, v_points, 'step_completed', NEW.id, v_org_id);

    -- 6. Insert into user_activities (with organization_id)
    INSERT INTO journeys.user_activities (user_id, type, points_awarded, metadata, organization_id)
    VALUES (
        NEW.user_id,
        'step_completed',
        v_points,
        jsonb_build_object(
            'step_id',       NEW.step_id,
            'enrollment_id', NEW.enrollment_id,
            'journey_id',    v_journey_id
        ),
        v_org_id
    );

    -- 7. Evaluate rewards (only when rewards_enabled)
    IF v_config IS NULL OR v_config.rewards_enabled = TRUE THEN

        -- 7a. step_completed rewards — FLAT format (legacy)
        --     unlock_condition: { "type": "step_completed", "step_id": "<uuid>" }
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

        -- 7b. step_completed rewards — NESTED format
        --     unlock_condition.conditions contains { "type": "step_completed", "step_id": "<uuid>" }
        FOR v_reward IN
            SELECT rc.id AS reward_id
            FROM journeys.rewards_catalog rc
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements(rc.unlock_condition->'conditions') AS cond
                WHERE cond->>'type' = 'step_completed'
                  AND cond->>'step_id' = NEW.step_id::TEXT
            )
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

        -- 7c. profile_completion rewards — awarded when the completed step is
        --     the configured profile-completion step for this org
        IF v_config IS NOT NULL
            AND v_config.profile_completion_step_id IS NOT NULL
            AND v_config.profile_completion_step_id = NEW.step_id
        THEN
            FOR v_reward IN
                SELECT rc.id AS reward_id
                FROM journeys.rewards_catalog rc
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(rc.unlock_condition->'conditions') AS cond
                    WHERE cond->>'type' = 'profile_completion'
                )
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
                    jsonb_build_object('trigger', 'profile_completion')
                );
            END LOOP;
        END IF;

        -- 8. points_threshold rewards (unchanged from previous version)
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

    END IF; -- rewards_enabled

    -- 9. Check if the entire journey is now complete
    --    (BEFORE trigger: new row not yet in table, so count + 1 = total after this insert)
    SELECT COUNT(*) INTO v_total_steps
    FROM journeys.steps
    WHERE journey_id = v_journey_id;

    SELECT COUNT(*) INTO v_completed_steps
    FROM journeys.step_completions
    WHERE enrollment_id = NEW.enrollment_id;

    IF v_total_steps > 0 AND (v_completed_steps + 1) >= v_total_steps THEN

        -- Auto-complete the enrollment
        UPDATE journeys.enrollments
        SET status       = 'completed',
            completed_at = NOW()
        WHERE id     = NEW.enrollment_id
          AND status != 'completed';

        -- Insert journey_completed activity (idempotent: skip if already logged)
        IF NOT EXISTS (
            SELECT 1 FROM journeys.user_activities
            WHERE user_id = NEW.user_id
              AND type    = 'journey_completed'
              AND metadata->>'journey_id' = v_journey_id::TEXT
        ) THEN
            INSERT INTO journeys.user_activities
                (user_id, type, points_awarded, metadata, organization_id)
            VALUES (
                NEW.user_id,
                'journey_completed',
                0,
                jsonb_build_object(
                    'journey_id',    v_journey_id,
                    'enrollment_id', NEW.enrollment_id
                ),
                v_org_id
            );
        END IF;

        -- Award journey_completed rewards (NESTED format)
        IF v_config IS NULL OR v_config.rewards_enabled = TRUE THEN
            FOR v_reward IN
                SELECT rc.id AS reward_id
                FROM journeys.rewards_catalog rc
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(rc.unlock_condition->'conditions') AS cond
                    WHERE cond->>'type' = 'journey_completed'
                      AND (
                          -- No journey_id specified → unlocks for any journey
                          cond->>'journey_id' IS NULL
                          -- Specific journey → must match
                          OR cond->>'journey_id' = v_journey_id::TEXT
                      )
                )
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
                    jsonb_build_object('trigger', 'journey_completed', 'journey_id', v_journey_id)
                );
            END LOOP;
        END IF;

    END IF; -- journey complete

    -- 10. Update enrollment.updated_at
    UPDATE journeys.enrollments
    SET updated_at = now()
    WHERE id = NEW.enrollment_id;

    -- 11. Store points earned on the step_completion row
    NEW.points_earned := v_points;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
SELECT '✅ MIGRATION: journey_completion_trigger applied' AS result;
SELECT '  - handle_step_completion() updated' AS detail;
SELECT '  - 7b: step_completed rewards (NESTED format) added' AS detail;
SELECT '  - 7c: profile_completion rewards when step = profile_completion_step_id' AS detail;
SELECT '  - 8: points_threshold rewards unchanged' AS detail;
SELECT '  - 9: auto-complete enrollment on last step' AS detail;
SELECT '  - 9: journey_completed activity inserted on completion' AS detail;
SELECT '  - 9: journey_completed rewards awarded on completion' AS detail;
