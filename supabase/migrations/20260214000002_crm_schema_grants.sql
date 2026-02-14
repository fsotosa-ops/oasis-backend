-- =============================================================================
-- MIGRATION: CRM Schema Grants
-- DATE: 2026-02-14
-- FIX: "permission denied for schema crm" — missing GRANT USAGE + table grants
-- =============================================================================

-- Schema-level access
GRANT USAGE ON SCHEMA crm TO service_role, authenticated;

-- Table-level access for service_role (admin client — full CRUD)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA crm TO service_role;

-- Table-level access for authenticated users (RLS policies still apply)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA crm TO authenticated;

-- Ensure future tables in crm schema inherit these grants
ALTER DEFAULT PRIVILEGES IN SCHEMA crm
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA crm
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
