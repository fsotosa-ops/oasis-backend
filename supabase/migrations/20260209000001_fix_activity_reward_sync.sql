-- =============================================================================
-- MIGRATION: Fix Activity & Reward Sync on Step/Journey Completion
-- =============================================================================
-- Problema: user_activities y user_rewards nunca se llenan porque el trigger
-- handle_step_completion() solo inserta en points_ledger.
--
-- Fix:
-- 1. Actualizar handle_step_completion() para insertar en user_activities
-- 2. Actualizar handle_step_completion() para evaluar rewards_catalog y otorgar user_rewards
-- 3. Crear trigger en enrollments para otorgar rewards al completar un journey
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Actualizar el trigger de completar step
-- -----------------------------------------------------------------------------
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

    -- 2. Determinar puntos
    IF v_step_config IS NOT NULL AND (v_step_config->>'points_base') IS NOT NULL THEN
        v_points := (v_step_config->>'points_base')::INTEGER;
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

-- -----------------------------------------------------------------------------
-- 2. Trigger para otorgar rewards al completar un journey
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION journeys.handle_enrollment_completion()
RETURNS TRIGGER AS $$
DECLARE
    v_reward RECORD;
BEGIN
    -- Solo actuar cuando el status cambia a 'completed'
    IF NEW.status = 'completed' AND (OLD.status IS NULL OR OLD.status <> 'completed') THEN

        -- Registrar actividad de journey completado
        INSERT INTO journeys.user_activities (user_id, type, points_awarded, metadata)
        VALUES (
            NEW.user_id,
            'journey_completed',
            0,
            jsonb_build_object(
                'journey_id', NEW.journey_id,
                'enrollment_id', NEW.id
            )
        );

        -- Evaluar rewards con unlock_condition de tipo journey_completed
        FOR v_reward IN
            SELECT rc.id AS reward_id
            FROM journeys.rewards_catalog rc
            WHERE rc.unlock_condition->>'type' = 'journey_completed'
              AND rc.unlock_condition->>'journey_id' = NEW.journey_id::TEXT
              AND NOT EXISTS (
                  SELECT 1 FROM journeys.user_rewards ur
                  WHERE ur.user_id = NEW.user_id AND ur.reward_id = rc.id
              )
        LOOP
            INSERT INTO journeys.user_rewards (user_id, reward_id, journey_id, metadata)
            VALUES (
                NEW.user_id,
                v_reward.reward_id,
                NEW.journey_id,
                jsonb_build_object('trigger', 'journey_completed', 'enrollment_id', NEW.id)
            );
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear trigger para enrollment completion
DROP TRIGGER IF EXISTS tr_reward_on_enrollment_completion ON journeys.enrollments;

CREATE TRIGGER tr_reward_on_enrollment_completion
AFTER UPDATE ON journeys.enrollments
FOR EACH ROW
EXECUTE FUNCTION journeys.handle_enrollment_completion();

-- -----------------------------------------------------------------------------
-- 3. Permisos: Asegurar que service_role tenga acceso a user_activities
-- -----------------------------------------------------------------------------
-- service_role ya tiene ALL gracias al GRANT original, pero explicitamos por seguridad
GRANT INSERT ON TABLE journeys.user_activities TO service_role;
GRANT INSERT ON TABLE journeys.user_rewards TO service_role;

SELECT '✅ MIGRATION APLICADA: user_activities y user_rewards ahora se llenan automáticamente' AS result;