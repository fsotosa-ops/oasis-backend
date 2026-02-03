-- =============================================================================
-- MASTER SCRIPT: JOURNEY SYSTEM & GAMIFICATION
-- =============================================================================
-- Este script configura TODA la capa de seguridad y lógica automática para
-- el esquema 'journeys'. Es idempotente (se puede correr varias veces).

-- -----------------------------------------------------------------------------
-- 1. ACCESO AL ESQUEMA Y TABLAS (La Capa Física)
-- -----------------------------------------------------------------------------

-- Abrir el esquema
GRANT USAGE ON SCHEMA journeys TO authenticated;
GRANT USAGE ON SCHEMA journeys TO service_role;

-- Dar permisos base de lectura a todo (RLS filtrará después)
GRANT SELECT ON ALL TABLES IN SCHEMA journeys TO authenticated;

-- Permisos de escritura para interacción de Usuario
GRANT INSERT, UPDATE ON TABLE journeys.enrollments TO authenticated;
GRANT INSERT ON TABLE journeys.step_completions TO authenticated;
GRANT INSERT ON TABLE journeys.user_activities TO authenticated;

-- Permisos de gestión para Admins (RLS validará el rol)
GRANT INSERT, UPDATE, DELETE ON TABLE journeys.journeys TO authenticated;
GRANT INSERT, UPDATE, DELETE ON TABLE journeys.steps TO authenticated;
GRANT INSERT, UPDATE, DELETE ON TABLE journeys.levels TO authenticated;
GRANT INSERT, UPDATE, DELETE ON TABLE journeys.rewards_catalog TO authenticated;

-- BLINDAJE: Nadie toca los puntos manualmente
REVOKE INSERT, UPDATE, DELETE ON TABLE journeys.points_ledger FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON TABLE journeys.user_rewards FROM authenticated;

-- Secuencias (IDs)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA journeys TO authenticated;


-- -----------------------------------------------------------------------------
-- 2. POLÍTICAS DE SEGURIDAD RLS (La Lógica de Acceso)
-- -----------------------------------------------------------------------------

-- Habilitar RLS en todo el esquema
ALTER TABLE journeys.journeys ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.levels ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.step_completions ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.points_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.rewards_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.user_rewards ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.user_activities ENABLE ROW LEVEL SECURITY;

-- --- JOURNEYS (Catálogo) ---
DROP POLICY IF EXISTS "read_journeys" ON journeys.journeys;
CREATE POLICY "read_journeys" ON journeys.journeys FOR SELECT USING (
    is_active = true 
    OR (EXISTS (SELECT 1 FROM journeys.enrollments WHERE journey_id = id AND user_id = auth.uid()))
    OR public.is_admin_secure()
);

DROP POLICY IF EXISTS "admin_journeys" ON journeys.journeys;
CREATE POLICY "admin_journeys" ON journeys.journeys FOR ALL USING (public.is_admin_secure());

-- --- STEPS (Pasos) ---
DROP POLICY IF EXISTS "read_steps" ON journeys.steps;
CREATE POLICY "read_steps" ON journeys.steps FOR SELECT USING (true); 

DROP POLICY IF EXISTS "admin_steps" ON journeys.steps;
CREATE POLICY "admin_steps" ON journeys.steps FOR ALL USING (public.is_admin_secure());

-- --- CONFIGURACIÓN (Levels & Rewards) ---
DROP POLICY IF EXISTS "read_config" ON journeys.levels;
CREATE POLICY "read_config" ON journeys.levels FOR SELECT USING (true);
DROP POLICY IF EXISTS "admin_config" ON journeys.levels;
CREATE POLICY "admin_config" ON journeys.levels FOR ALL USING (public.is_admin_secure());

DROP POLICY IF EXISTS "read_catalog" ON journeys.rewards_catalog;
CREATE POLICY "read_catalog" ON journeys.rewards_catalog FOR SELECT USING (true);
DROP POLICY IF EXISTS "admin_catalog" ON journeys.rewards_catalog;
CREATE POLICY "admin_catalog" ON journeys.rewards_catalog FOR ALL USING (public.is_admin_secure());

-- --- USUARIO (Datos Privados) ---
DROP POLICY IF EXISTS "own_enrollments" ON journeys.enrollments;
CREATE POLICY "own_enrollments" ON journeys.enrollments FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS "own_completions" ON journeys.step_completions;
CREATE POLICY "own_completions" ON journeys.step_completions FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS "own_ledger" ON journeys.points_ledger;
CREATE POLICY "own_ledger" ON journeys.points_ledger FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "own_rewards" ON journeys.user_rewards;
CREATE POLICY "own_rewards" ON journeys.user_rewards FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS "own_activity" ON journeys.user_activities;
CREATE POLICY "own_activity" ON journeys.user_activities FOR ALL USING (user_id = auth.uid());


-- -----------------------------------------------------------------------------
-- 3. AUTOMATIZACIÓN (El Cerebro)
-- -----------------------------------------------------------------------------
-- Trigger: Cuando un usuario completa un paso -> El sistema le da puntos automáticamente.

CREATE OR REPLACE FUNCTION journeys.handle_step_completion()
RETURNS TRIGGER AS $$
DECLARE
    v_points INTEGER := 10; -- Valor por defecto
    v_step_config JSONB;
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
    -- Al ser SECURITY DEFINER (implícito), esto salta el bloqueo de REVOKE.
    INSERT INTO journeys.points_ledger (user_id, amount, reason, reference_id)
    VALUES (NEW.user_id, v_points, 'step_completed', NEW.id);

    -- 4. Actualizar Enrollment
    UPDATE journeys.enrollments
    SET updated_at = now()
    WHERE id = NEW.enrollment_id;
    
    -- 5. Guardar puntos ganados en el registro histórico
    NEW.points_earned := v_points;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recrear el Trigger
DROP TRIGGER IF EXISTS tr_award_points_on_completion ON journeys.step_completions;

CREATE TRIGGER tr_award_points_on_completion
BEFORE INSERT ON journeys.step_completions
FOR EACH ROW
EXECUTE FUNCTION journeys.handle_step_completion();

SELECT '✅ SISTEMA COMPLETO APLICADO: Permisos + RLS + Trigger de Puntos' as result;