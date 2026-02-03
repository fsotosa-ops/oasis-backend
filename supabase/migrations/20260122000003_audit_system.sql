-- =============================================================================
-- MIGRATION: Audit System
-- =============================================================================
-- Creates audit logging infrastructure in a separate schema.
-- Immutable logs for compliance and debugging.
-- =============================================================================

-- =============================================================================
-- 1. SCHEMA & PERMISSIONS
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS audit;

-- Grant access to roles
GRANT USAGE ON SCHEMA audit TO service_role;
GRANT USAGE ON SCHEMA audit TO postgres;
GRANT USAGE ON SCHEMA audit TO anon;
GRANT USAGE ON SCHEMA audit TO authenticated;

-- Full access for service_role (backend)
GRANT ALL ON ALL TABLES IN SCHEMA audit TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA audit TO service_role;

-- Auto-grant for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT ALL ON SEQUENCES TO service_role;

-- Read-only for authenticated users
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO authenticated;

-- Block writes from normal users
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA audit FROM authenticated;
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA audit FROM anon;

-- =============================================================================
-- 2. TABLES
-- =============================================================================

-- Categories (Master table)
CREATE TABLE IF NOT EXISTS audit.categories (
    code TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT,
    retention_days INT DEFAULT 365,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed categories
INSERT INTO audit.categories (code, label, description) VALUES
    ('auth', 'Seguridad', 'Logins, registro, logout'),
    ('org', 'Organización', 'Cambios en empresa, miembros e invitaciones'),
    ('billing', 'Facturación', 'Pagos y suscripciones'),
    ('journey', 'Experiencia', 'Avance de usuarios en journeys'),
    ('system', 'Sistema', 'Errores y tareas automáticas')
ON CONFLICT (code) DO NOTHING;

-- Logs table (The audit trail)
CREATE TABLE IF NOT EXISTS audit.logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at TIMESTAMPTZ DEFAULT NOW(),

    -- Who and Where
    organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    actor_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_email TEXT,  -- Snapshot in case user is deleted

    -- What
    category_code TEXT REFERENCES audit.categories(code),
    action TEXT NOT NULL,

    -- Details
    resource TEXT,
    resource_id UUID,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Technical context
    ip_address INET,
    user_agent TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit.logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit.logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit.logs(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_category ON audit.logs(category_code);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit.logs(action);

-- =============================================================================
-- 3. ROW LEVEL SECURITY
-- =============================================================================
ALTER TABLE audit.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.logs ENABLE ROW LEVEL SECURITY;

-- Categories are public to read
CREATE POLICY "audit_categories_select_all"
ON audit.categories FOR SELECT
USING (TRUE);

-- Platform Admins see all logs
CREATE POLICY "audit_logs_select_platform_admin"
ON audit.logs FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND is_platform_admin = TRUE
    )
);

-- Org Owners/Admins see their org's logs
CREATE POLICY "audit_logs_select_org_admin"
ON audit.logs FOR SELECT
USING (
    organization_id IN (
        SELECT organization_id FROM public.organization_members
        WHERE user_id = auth.uid()
        AND role IN ('owner', 'admin')
        AND status = 'active'
    )
);

-- Users see their own logs
CREATE POLICY "audit_logs_select_own"
ON audit.logs FOR SELECT
USING (actor_id = auth.uid());

-- =============================================================================
-- 4. IMMUTABILITY (Hardening)
-- =============================================================================
CREATE OR REPLACE FUNCTION audit.prevent_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs are immutable. Cannot update or delete.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS check_audit_immutable ON audit.logs;
CREATE TRIGGER check_audit_immutable
BEFORE UPDATE OR DELETE ON audit.logs
FOR EACH ROW
EXECUTE FUNCTION audit.prevent_log_modification();

-- =============================================================================
-- DONE
-- =============================================================================
COMMENT ON SCHEMA audit IS 'Immutable audit logging system';
