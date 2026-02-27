-- =============================================================================
-- MIGRATION: Add profile_field to journeys.step_type enum
-- =============================================================================
-- Agrega el tipo de step profile_field para el Journey de Onboarding preseteado.
-- Cada step de tipo profile_field representa uno o más campos del perfil CRM.
-- =============================================================================

ALTER TYPE journeys.step_type ADD VALUE IF NOT EXISTS 'profile_field';
