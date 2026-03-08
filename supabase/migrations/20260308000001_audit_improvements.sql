-- =============================================================================
-- MIGRATION: Audit System Improvements
-- =============================================================================
-- Closes audit debt identified in audit review 2026-03-08:
--   1. Missing categories: crm, event, resource
--   2. Missing indexes: audit.logs.resource_id, crm.contact_changes.changed_by
--   3. Helper function audit.log_change() for internal/trigger use
--   4. DB triggers on organizations, organization_members, crm.org_events
-- =============================================================================

-- =============================================================================
-- SECTION 1: Insert missing audit categories
-- MUST be first — trigger functions below reference these codes via FK
-- =============================================================================
INSERT INTO audit.categories (code, label, description) VALUES
    ('crm',      'CRM',     'Cambios en contactos, notas y tareas del CRM'),
    ('event',    'Evento',  'Creación, modificación y eliminación de eventos'),
    ('resource', 'Recurso', 'Acceso y gestión de recursos educativos')
ON CONFLICT (code) DO NOTHING;

-- =============================================================================
-- SECTION 2: Missing indexes
-- =============================================================================

-- audit.logs: enables "show all changes to resource X" without seq scan
CREATE INDEX IF NOT EXISTS idx_audit_resource_id
    ON audit.logs(resource_id);

-- crm.contact_changes: enables "what did admin Y change" without seq scan
CREATE INDEX IF NOT EXISTS idx_crm_contact_changes_changed_by
    ON crm.contact_changes(changed_by);

-- =============================================================================
-- SECTION 3: Helper function audit.log_change()
-- =============================================================================
-- Internal use only — NOT granted to 'authenticated'.
-- Mimics the security pattern of public.log_auth_event().
-- Called by trigger functions (SECURITY DEFINER runs as postgres).
-- =============================================================================
CREATE OR REPLACE FUNCTION audit.log_change(
    p_category        TEXT,
    p_action          TEXT,
    p_resource        TEXT,
    p_resource_id     UUID,
    p_organization_id UUID,
    p_actor_id        UUID,
    p_actor_email     TEXT,
    p_metadata        JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, audit
AS $$
DECLARE
    v_log_id UUID;
BEGIN
    INSERT INTO audit.logs (
        organization_id,
        actor_id,
        actor_email,
        category_code,
        action,
        resource,
        resource_id,
        metadata
    ) VALUES (
        p_organization_id,
        p_actor_id,
        p_actor_email,
        p_category,
        p_action,
        p_resource,
        p_resource_id,
        COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_log_id;

    RETURN v_log_id;
END;
$$;

-- Only service_role (Python backend) and postgres may call this directly.
-- Trigger functions also use it via SECURITY DEFINER (execute as postgres).
GRANT EXECUTE ON FUNCTION audit.log_change(TEXT, TEXT, TEXT, UUID, UUID, UUID, TEXT, JSONB)
    TO service_role;
GRANT EXECUTE ON FUNCTION audit.log_change(TEXT, TEXT, TEXT, UUID, UUID, UUID, TEXT, JSONB)
    TO postgres;

-- =============================================================================
-- SECTION 4: Trigger functions + triggers
-- Actor resolution pattern mirrors crm.log_contact_field_changes():
--   current_setting('app.acting_user_id') → auth.uid() fallback
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 4a. public.organizations → category 'org'
--     Actions: ORG_CREATED | ORG_UPDATED | ORG_DELETED
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION audit.trg_log_organizations()
RETURNS TRIGGER AS $$
DECLARE
    _actor_id    UUID;
    _actor_email TEXT;
    _action      TEXT;
    _resource_id UUID;
    _org_id      UUID;
    _metadata    JSONB;
BEGIN
    -- Resolve actor: app context (Python backend sets this) → JWT fallback
    BEGIN
        _actor_id := current_setting('app.acting_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        _actor_id := NULL;
    END;
    IF _actor_id IS NULL THEN _actor_id := auth.uid(); END IF;

    IF _actor_id IS NOT NULL THEN
        SELECT email INTO _actor_email FROM public.profiles WHERE id = _actor_id;
    END IF;

    IF TG_OP = 'INSERT' THEN
        _action      := 'ORG_CREATED';
        _resource_id := NEW.id;
        _org_id      := NEW.id;
        _metadata    := jsonb_build_object(
            'name', NEW.name, 'slug', NEW.slug, 'type', NEW.type
        );
    ELSIF TG_OP = 'UPDATE' THEN
        _action      := 'ORG_UPDATED';
        _resource_id := NEW.id;
        _org_id      := NEW.id;
        _metadata    := jsonb_build_object(
            'name', NEW.name, 'slug', NEW.slug, 'type', NEW.type
        );
    ELSE -- DELETE
        _action      := 'ORG_DELETED';
        _resource_id := OLD.id;
        _org_id      := OLD.id;
        _metadata    := jsonb_build_object(
            'name', OLD.name, 'slug', OLD.slug, 'type', OLD.type
        );
    END IF;

    PERFORM audit.log_change(
        'org', _action, 'organizations', _resource_id, _org_id,
        _actor_id, _actor_email, _metadata
    );

    RETURN NULL; -- AFTER trigger: return value is ignored
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, audit;

DROP TRIGGER IF EXISTS trg_audit_organizations ON public.organizations;
CREATE TRIGGER trg_audit_organizations
AFTER INSERT OR UPDATE OR DELETE ON public.organizations
FOR EACH ROW EXECUTE FUNCTION audit.trg_log_organizations();

-- ─────────────────────────────────────────────────────────────────────────────
-- 4b. public.organization_members → category 'org'
--     Actions: MEMBER_ADDED | MEMBER_UPDATED | MEMBER_REMOVED
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION audit.trg_log_organization_members()
RETURNS TRIGGER AS $$
DECLARE
    _actor_id    UUID;
    _actor_email TEXT;
    _action      TEXT;
    _resource_id UUID;
    _org_id      UUID;
    _metadata    JSONB;
BEGIN
    BEGIN
        _actor_id := current_setting('app.acting_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        _actor_id := NULL;
    END;
    IF _actor_id IS NULL THEN _actor_id := auth.uid(); END IF;

    IF _actor_id IS NOT NULL THEN
        SELECT email INTO _actor_email FROM public.profiles WHERE id = _actor_id;
    END IF;

    IF TG_OP = 'INSERT' THEN
        _action      := 'MEMBER_ADDED';
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object(
            'user_id', NEW.user_id,
            'role',    NEW.role,
            'status',  NEW.status
        );
    ELSIF TG_OP = 'UPDATE' THEN
        _action      := 'MEMBER_UPDATED';
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object(
            'user_id',    NEW.user_id,
            'role',       NEW.role,
            'old_role',   OLD.role,
            'status',     NEW.status,
            'old_status', OLD.status
        );
    ELSE -- DELETE
        _action      := 'MEMBER_REMOVED';
        _resource_id := OLD.id;
        _org_id      := OLD.organization_id;
        _metadata    := jsonb_build_object(
            'user_id', OLD.user_id,
            'role',    OLD.role,
            'status',  OLD.status
        );
    END IF;

    PERFORM audit.log_change(
        'org', _action, 'organization_members', _resource_id, _org_id,
        _actor_id, _actor_email, _metadata
    );

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, audit;

DROP TRIGGER IF EXISTS trg_audit_organization_members ON public.organization_members;
CREATE TRIGGER trg_audit_organization_members
AFTER INSERT OR UPDATE OR DELETE ON public.organization_members
FOR EACH ROW EXECUTE FUNCTION audit.trg_log_organization_members();

-- ─────────────────────────────────────────────────────────────────────────────
-- 4c. crm.org_events → category 'event'
--     Actions: EVENT_CREATED | EVENT_UPDATED | EVENT_STATUS_CHANGED | EVENT_DELETED
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION audit.trg_log_org_events()
RETURNS TRIGGER AS $$
DECLARE
    _actor_id    UUID;
    _actor_email TEXT;
    _action      TEXT;
    _resource_id UUID;
    _org_id      UUID;
    _metadata    JSONB;
BEGIN
    BEGIN
        _actor_id := current_setting('app.acting_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        _actor_id := NULL;
    END;
    IF _actor_id IS NULL THEN _actor_id := auth.uid(); END IF;

    IF _actor_id IS NOT NULL THEN
        SELECT email INTO _actor_email FROM public.profiles WHERE id = _actor_id;
    END IF;

    IF TG_OP = 'INSERT' THEN
        _action      := 'EVENT_CREATED';
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object(
            'name', NEW.name, 'slug', NEW.slug, 'status', NEW.status
        );
    ELSIF TG_OP = 'UPDATE' THEN
        -- Status change warrants a distinct action for easier filtering
        IF OLD.status IS DISTINCT FROM NEW.status THEN
            _action := 'EVENT_STATUS_CHANGED';
        ELSE
            _action := 'EVENT_UPDATED';
        END IF;
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object(
            'name',       NEW.name,
            'slug',       NEW.slug,
            'status',     NEW.status,
            'old_status', OLD.status
        );
    ELSE -- DELETE
        _action      := 'EVENT_DELETED';
        _resource_id := OLD.id;
        _org_id      := OLD.organization_id;
        _metadata    := jsonb_build_object(
            'name', OLD.name, 'slug', OLD.slug, 'status', OLD.status
        );
    END IF;

    PERFORM audit.log_change(
        'event', _action, 'org_events', _resource_id, _org_id,
        _actor_id, _actor_email, _metadata
    );

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, audit, crm;

DROP TRIGGER IF EXISTS trg_audit_org_events ON crm.org_events;
CREATE TRIGGER trg_audit_org_events
AFTER INSERT OR UPDATE OR DELETE ON crm.org_events
FOR EACH ROW EXECUTE FUNCTION audit.trg_log_org_events();

-- =============================================================================
-- DONE
-- =============================================================================
COMMENT ON FUNCTION audit.log_change IS
    'Internal helper for trigger-based audit logging. Not callable by authenticated users.';

SELECT '✅ MIGRATION: audit_improvements applied' AS result;
SELECT '  - 3 categories added (crm, event, resource)' AS detail;
SELECT '  - 2 indexes added (audit.logs.resource_id, crm.contact_changes.changed_by)' AS detail;
SELECT '  - audit.log_change() created' AS detail;
SELECT '  - Triggers: organizations, organization_members, crm.org_events' AS detail;
