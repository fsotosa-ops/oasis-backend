-- =============================================================================
-- MIGRATION: Rename points_base → base_points in gamification_rules JSONB
-- =============================================================================
-- Problema: Frontend envía base_points, backend Pydantic esperaba points_base.
-- Los puntos nunca se persistían porque Pydantic ignoraba el campo desconocido.
-- =============================================================================

-- 1. Renombrar key en JSONB existentes
UPDATE journeys.steps
SET gamification_rules = gamification_rules - 'points_base'
    || jsonb_build_object('base_points', COALESCE((gamification_rules->>'points_base')::int, 0))
WHERE gamification_rules ? 'points_base';

-- 2. Actualizar default de la columna
ALTER TABLE journeys.steps
ALTER COLUMN gamification_rules SET DEFAULT '{"base_points": 0}'::jsonb;

-- 3. Actualizar handle_step_completion() para leer base_points
CREATE OR REPLACE FUNCTION journeys.handle_step_completion()
RETURNS TRIGGER AS $$
DECLARE
    v_points INTEGER := 10;
    v_step_config JSONB;
    v_journey_id UUID;
    v_reward RECORD;
BEGIN
    -- 1. Buscar configuración del paso
    SELECT gamification_rules INTO v_step_config
    FROM journeys.steps
    WHERE id = NEW.step_id;

    -- 2. Determinar puntos (ahora lee base_points)
    IF v_step_config IS NOT NULL AND (v_step_config->>'base_points') IS NOT NULL THEN
        v_points := (v_step_config->>'base_points')::INTEGER;
    END IF;

    -- 3. Insertar en Ledger (Libro de Puntos)
    INSERT INTO journeys.points_ledger (user_id, amount, reason, reference_id)
    VALUES (NEW.user_id, v_points, 'step_completed', NEW.id);

    -- 4. Insertar en user_activities (registro de actividad)
    INSERT INTO journeys.user_activities (user_id, type, points_awarded, metadata)
    VALUES (
        NEW.user_id,
        'step_completed',
        v_points,
        jsonb_build_object(
            'step_id', NEW.step_id,
            'enrollment_id', NEW.enrollment_id,
            'journey_id', NEW.journey_id
        )
    );

    -- 5. Obtener journey_id para evaluar rewards
    v_journey_id := NEW.journey_id;

    -- 6. Evaluar rewards con unlock_condition de tipo step_completed
    FOR v_reward IN
        SELECT rc.id AS reward_id
        FROM journeys.rewards_catalog rc
        WHERE rc.unlock_condition->>'type' = 'step_completed'
          AND rc.unlock_condition->>'step_id' = NEW.step_id::TEXT
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

    -- 7. Evaluar rewards con unlock_condition de tipo points_threshold
    FOR v_reward IN
        SELECT rc.id AS reward_id
        FROM journeys.rewards_catalog rc
        WHERE rc.unlock_condition->>'type' = 'points_threshold'
          AND (rc.unlock_condition->>'min_points')::INTEGER
              <= journeys.get_user_total_points(NEW.user_id) + v_points
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

    -- 8. Actualizar Enrollment
    UPDATE journeys.enrollments
    SET updated_at = now()
    WHERE id = NEW.enrollment_id;

    -- 9. Guardar puntos ganados en el registro histórico
    NEW.points_earned := v_points;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

SELECT '✅ MIGRATION: points_base renamed to base_points everywhere' AS result;
