-- =============================================================================
-- MIGRATION: Change reward_type from ENUM to TEXT
-- =============================================================================
-- Problema: El ENUM solo permite 'badge' y 'points'. Las organizaciones
-- necesitan definir sus propios tipos (certificado, descuento, acceso, etc.)
-- =============================================================================

-- 1. Cambiar columna de ENUM a TEXT
ALTER TABLE journeys.rewards_catalog
ALTER COLUMN type TYPE TEXT USING type::TEXT;

-- 2. Eliminar el ENUM (ya no se usa)
DROP TYPE IF EXISTS journeys.reward_type;

SELECT '✅ MIGRATION: reward_type is now TEXT — organizations can define custom types' AS result;
