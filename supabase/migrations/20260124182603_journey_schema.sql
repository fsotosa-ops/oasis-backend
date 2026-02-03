-- =============================================================================
-- MIGRATION: OASIS Journey Service (Full Schema)
-- =============================================================================
-- Servicio: Journey & Gamification Engine
-- Descripción: Maneja la experiencia del usuario, progresión, niveles y recompensas.
-- Dependencias: public.profiles, public.organizations
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS journeys;

-- =============================================================================
-- 1. ENUMS & TYPES
-- =============================================================================

-- Tipos de pasos expandidos para incluir interacciones modernas
DO $$ BEGIN
    CREATE TYPE journeys.step_type AS ENUM (
        'survey',               -- Typeform / Encuestas
        'event_attendance',     -- Zoom / Presencial
        'content_view',         -- Video / PDF
        'milestone',            -- Hito lógico
        'social_interaction',   -- Post en foro / Like
        'resource_consumption'  -- Lectura de artículos
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE journeys.enrollment_status AS ENUM ('active', 'completed', 'pending', 'dropped');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE journeys.reward_type AS ENUM ('badge', 'points');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =============================================================================
-- 2. CORE TABLES (JOURNEY ENGINE)
-- =============================================================================

-- Journeys: Las "Rutas" de experiencia
CREATE TABLE IF NOT EXISTS journeys.journeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT,
    thumbnail_url TEXT,

    is_active BOOLEAN DEFAULT TRUE,

    -- Configuración global del journey (ej: fecha inicio/fin, prerequisitos)
    metadata JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_journey_slug_per_org UNIQUE (organization_id, slug)
);

-- Pasos: Los bloques constructivos
CREATE TABLE IF NOT EXISTS journeys.steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journey_id UUID NOT NULL REFERENCES journeys.journeys(id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    type journeys.step_type NOT NULL,
    order_index INT NOT NULL,

    -- Configuración técnica (ej: ID de Typeform, URL de Video)
    config JSONB DEFAULT '{}'::jsonb,

    -- MOTOR DE GAMIFICACIÓN DATA-DRIVEN
    -- Define cuántos puntos da y bajo qué condiciones (ej: "min_duration": 60)
    gamification_rules JSONB DEFAULT '{ "points_base": 0 }'::jsonb,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Inscripciones: Vincula Usuario <-> Journey
CREATE TABLE IF NOT EXISTS journeys.enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journey_id UUID NOT NULL REFERENCES journeys.journeys(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,

    status journeys.enrollment_status DEFAULT 'active',
    current_step_index INT DEFAULT 0,

    -- Métricas calculadas para acceso rápido
    progress_percentage FLOAT DEFAULT 0.0,

    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    CONSTRAINT unique_user_journey UNIQUE (journey_id, user_id)
);

-- Progreso detallado: Cada paso completado
-- Denormalizado con user_id y journey_id para queries de analytics sin JOINs
CREATE TABLE IF NOT EXISTS journeys.step_completions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES journeys.enrollments(id) ON DELETE CASCADE,
    step_id UUID NOT NULL REFERENCES journeys.steps(id) ON DELETE CASCADE,

    -- Denormalizados para queries directas (llenados por trigger)
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    journey_id UUID NOT NULL REFERENCES journeys.journeys(id) ON DELETE CASCADE,

    completed_at TIMESTAMPTZ DEFAULT NOW(),
    points_earned INT DEFAULT 0,

    -- Trazabilidad externa (ej: response_id de Typeform)
    external_reference TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    CONSTRAINT unique_step_per_enrollment UNIQUE (enrollment_id, step_id)
);

-- =============================================================================
-- 3. GAMIFICATION ENGINE TABLES
-- =============================================================================

-- Niveles Dinámicos (Configurables por Organización)
CREATE TABLE IF NOT EXISTS journeys.levels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,

    name TEXT NOT NULL,          -- Ej: "Semilla", "Brote", "Árbol"
    min_points INT NOT NULL,     -- Puntos necesarios para alcanzarlo

    icon_url TEXT,
    benefits JSONB DEFAULT '{}'::jsonb, -- Ej: {"can_create_events": true}

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, min_points)
);

-- Actividades "Side-Quest" (Fuera de un Journey lineal)
-- Ej: Comentar en el foro, Dar like, Ver un recurso suelto
CREATE TABLE IF NOT EXISTS journeys.user_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,

    type TEXT NOT NULL, -- 'social_post', 'resource_view'
    points_awarded INT DEFAULT 0,

    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Catálogo de Recompensas (Insignias)
CREATE TABLE IF NOT EXISTS journeys.rewards_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,

    name TEXT NOT NULL,
    description TEXT,
    type journeys.reward_type NOT NULL,
    icon_url TEXT,

    -- Reglas automáticas para otorgarla (ej: "complete_journey_xyz")
    unlock_condition JSONB DEFAULT '{}'::jsonb
);

-- Inventario de Recompensas del Usuario
CREATE TABLE IF NOT EXISTS journeys.user_rewards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    reward_id UUID NOT NULL REFERENCES journeys.rewards_catalog(id) ON DELETE CASCADE,

    earned_at TIMESTAMPTZ DEFAULT NOW(),
    journey_id UUID REFERENCES journeys.journeys(id) ON DELETE SET NULL,

    metadata JSONB DEFAULT '{}'::jsonb
);

-- Ledger Transaccional de Puntos (Auditoría de Gamificación)
CREATE TABLE IF NOT EXISTS journeys.points_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    amount INT NOT NULL,

    reason TEXT NOT NULL, -- ej: 'step_completed', 'daily_login', 'manual_adjustment'
    reference_id UUID,    -- ID de la actividad o step que generó los puntos

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 4. TRIGGERS & INDEXES
-- =============================================================================

CREATE TRIGGER update_journeys_timestamp BEFORE UPDATE ON journeys.journeys
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_steps_timestamp BEFORE UPDATE ON journeys.steps
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Índices optimizados para consultas frecuentes del Frontend
CREATE INDEX idx_journeys_org ON journeys.journeys(organization_id);
CREATE INDEX idx_steps_journey ON journeys.steps(journey_id, order_index);
CREATE INDEX idx_enrollments_user_status ON journeys.enrollments(user_id, status);
CREATE INDEX idx_activities_user_date ON journeys.user_activities(user_id, created_at DESC);
CREATE INDEX idx_ledger_user_sum ON journeys.points_ledger(user_id);

-- =============================================================================
-- 5. ROW LEVEL SECURITY (POLICIES)
-- =============================================================================

-- Habilitar RLS en todas las tablas
ALTER TABLE journeys.journeys ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.step_completions ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.levels ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.user_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.rewards_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.user_rewards ENABLE ROW LEVEL SECURITY;
ALTER TABLE journeys.points_ledger ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- Policy: JOURNEYS & STEPS (Lectura pública para miembros de la org)
-- -----------------------------------------------------------------------------
CREATE POLICY "View Journeys: Members of Org" ON journeys.journeys
    FOR SELECT USING (
        organization_id IN (SELECT public.get_my_org_ids())
        OR
        -- Permitir ver journeys públicos de la comunidad OASIS
        organization_id = (SELECT id FROM public.organizations WHERE slug = 'oasis-community')
    );

CREATE POLICY "View Steps: Access via Journey" ON journeys.steps
    FOR SELECT USING (
        journey_id IN (
            SELECT id FROM journeys.journeys
            WHERE organization_id IN (SELECT public.get_my_org_ids())
            OR organization_id = (SELECT id FROM public.organizations WHERE slug = 'oasis-community')
        )
    );

-- -----------------------------------------------------------------------------
-- Policy: USER DATA (Solo el dueño puede ver sus datos)
-- -----------------------------------------------------------------------------
CREATE POLICY "Enrollments: Own Data" ON journeys.enrollments
    FOR ALL USING (user_id = auth.uid());

-- Ahora usa user_id directo (denormalizado) - más eficiente
CREATE POLICY "Completions: Own Data" ON journeys.step_completions
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Activities: Own Data" ON journeys.user_activities
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Points: Own Data" ON journeys.points_ledger
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Rewards: Own Data" ON journeys.user_rewards
    FOR SELECT USING (user_id = auth.uid());

-- -----------------------------------------------------------------------------
-- Policy: CONFIG DATA (Niveles y Catálogo)
-- -----------------------------------------------------------------------------
CREATE POLICY "Levels: View Org Levels" ON journeys.levels
    FOR SELECT USING (
        organization_id IN (SELECT public.get_my_org_ids())
        OR organization_id IS NULL -- Niveles globales por defecto
    );

CREATE POLICY "Rewards Catalog: View Org Rewards" ON journeys.rewards_catalog
    FOR SELECT USING (
        organization_id IN (SELECT public.get_my_org_ids())
        OR organization_id IS NULL -- Insignias globales
    );

-- -----------------------------------------------------------------------------
-- Service Role Access (Backend)
-- -----------------------------------------------------------------------------
-- Nota: El 'service_role' de Supabase (tu API Python) se salta el RLS por defecto,
-- pero es buena práctica declarar permisos explícitos si usas clientes restringidos.
GRANT USAGE ON SCHEMA journeys TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA journeys TO service_role;

-- =============================================================================
-- 6. FUNCTIONS (RPCs)
-- =============================================================================

-- Función para calcular puntos totales de un usuario
CREATE OR REPLACE FUNCTION journeys.get_user_total_points(uid UUID)
RETURNS INTEGER
LANGUAGE SQL
STABLE
SECURITY DEFINER
AS $$
    SELECT COALESCE(SUM(amount), 0)::INTEGER
    FROM journeys.points_ledger
    WHERE user_id = uid;
$$;

-- Función para obtener el nivel actual del usuario basado en sus puntos
CREATE OR REPLACE FUNCTION journeys.get_user_current_level(uid UUID, org_id UUID DEFAULT NULL)
RETURNS TABLE(level_id UUID, level_name TEXT, min_points INT, next_level_points INT)
LANGUAGE SQL
STABLE
SECURITY DEFINER
AS $$
    WITH user_points AS (
        SELECT journeys.get_user_total_points(uid) AS total
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
        SELECT l.min_points
        FROM journeys.levels l, user_points up
        WHERE (l.organization_id = org_id OR l.organization_id IS NULL)
          AND l.min_points > up.total
        ORDER BY l.min_points ASC
        LIMIT 1
    )
    SELECT
        cl.id AS level_id,
        cl.name AS level_name,
        cl.min_points,
        nl.min_points AS next_level_points
    FROM current_level cl
    LEFT JOIN next_level nl ON true;
$$;

-- Función para calcular progreso de un enrollment
CREATE OR REPLACE FUNCTION journeys.calculate_enrollment_progress(enrollment_uuid UUID)
RETURNS FLOAT
LANGUAGE SQL
STABLE
AS $$
    WITH enrollment_data AS (
        SELECT e.id, e.journey_id
        FROM journeys.enrollments e
        WHERE e.id = enrollment_uuid
    ),
    total_steps AS (
        SELECT COUNT(*)::FLOAT AS count
        FROM journeys.steps s, enrollment_data ed
        WHERE s.journey_id = ed.journey_id
    ),
    completed_steps AS (
        SELECT COUNT(*)::FLOAT AS count
        FROM journeys.step_completions sc
        WHERE sc.enrollment_id = enrollment_uuid
    )
    SELECT
        CASE
            WHEN ts.count = 0 THEN 0
            ELSE ROUND((cs.count / ts.count * 100)::NUMERIC, 2)::FLOAT
        END
    FROM total_steps ts, completed_steps cs;
$$;

-- =============================================================================
-- 7. ADDITIONAL INDEXES
-- =============================================================================

-- Índice para búsqueda rápida de completions por enrollment
CREATE INDEX IF NOT EXISTS idx_completions_enrollment_step
ON journeys.step_completions(enrollment_id, step_id);

-- Índices para columnas denormalizadas (queries de analytics)
CREATE INDEX IF NOT EXISTS idx_completions_user
ON journeys.step_completions(user_id);

CREATE INDEX IF NOT EXISTS idx_completions_journey
ON journeys.step_completions(journey_id);

CREATE INDEX IF NOT EXISTS idx_completions_journey_step
ON journeys.step_completions(journey_id, step_id);

-- Índice para búsqueda de rewards por usuario
CREATE INDEX IF NOT EXISTS idx_user_rewards_user
ON journeys.user_rewards(user_id);

-- Índice para steps por ID (usado en tracking)
CREATE INDEX IF NOT EXISTS idx_steps_id
ON journeys.steps(id);

-- =============================================================================
-- 8. ADDITIONAL TRIGGERS
-- =============================================================================

-- Trigger para actualizar timestamp en enrollments
CREATE TRIGGER update_enrollments_timestamp
BEFORE UPDATE ON journeys.enrollments
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Trigger para auto-llenar user_id y journey_id en step_completions
CREATE OR REPLACE FUNCTION journeys.fill_completion_denormalized_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id UUID;
    v_journey_id UUID;
BEGIN
    -- Obtener user_id y journey_id del enrollment
    SELECT e.user_id, e.journey_id
    INTO v_user_id, v_journey_id
    FROM journeys.enrollments e
    WHERE e.id = NEW.enrollment_id;

    -- Llenar campos denormalizados
    NEW.user_id := v_user_id;
    NEW.journey_id := v_journey_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER before_step_completion_fill_fields
BEFORE INSERT ON journeys.step_completions
FOR EACH ROW EXECUTE FUNCTION journeys.fill_completion_denormalized_fields();

-- Trigger para actualizar progreso automáticamente al completar un step
CREATE OR REPLACE FUNCTION journeys.update_enrollment_progress()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE journeys.enrollments
    SET
        progress_percentage = journeys.calculate_enrollment_progress(NEW.enrollment_id),
        current_step_index = (
            SELECT COUNT(*)
            FROM journeys.step_completions
            WHERE enrollment_id = NEW.enrollment_id
        )
    WHERE id = NEW.enrollment_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER on_step_completion_update_progress
AFTER INSERT ON journeys.step_completions
FOR EACH ROW EXECUTE FUNCTION journeys.update_enrollment_progress();

-- =============================================================================
-- 9. ADDITIONAL RLS POLICIES
-- =============================================================================

-- Policy explícita para INSERT en enrollments (usuario solo puede inscribirse a sí mismo)
CREATE POLICY "Enrollments: User can enroll self" ON journeys.enrollments
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- Policy para INSERT en user_activities
CREATE POLICY "Activities: User can insert own" ON journeys.user_activities
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- Policy para INSERT en step_completions
-- El trigger llena user_id automáticamente, validamos que el enrollment sea del usuario
CREATE POLICY "Completions: Insert own" ON journeys.step_completions
    FOR INSERT WITH CHECK (
        enrollment_id IN (SELECT id FROM journeys.enrollments WHERE user_id = auth.uid())
    );

-- =============================================================================
-- 10. GRANT EXECUTE ON FUNCTIONS
-- =============================================================================

GRANT EXECUTE ON FUNCTION journeys.get_user_total_points(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION journeys.get_user_current_level(UUID, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION journeys.calculate_enrollment_progress(UUID) TO authenticated;
