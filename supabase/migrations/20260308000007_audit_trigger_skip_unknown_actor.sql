-- =============================================================================
-- MIGRATION: Audit triggers — skip when actor cannot be resolved
-- =============================================================================
-- Problem:
--   When Python backend uses the admin client (service_role) for operations
--   like create_org, auth.uid() = NULL and app.acting_user_id is not set.
--   The triggers fire and INSERT audit records with NULL actor_id.
--
-- Solution:
--   Triggers skip (RETURN NULL) when actor_id cannot be determined.
--   Python backend is responsible for writing explicit audit logs for all
--   admin-client operations (it knows the actor from the request context).
--
-- User-token operations (invite, update, remove member, update_org, delete_org)
--   are NOT affected — auth.uid() is set by PostgREST and resolves correctly.
--
-- Side effect: direct SQL changes in SQL Editor won't be audited either,
--   because postgres/service_role also has no JWT context.
--   This is acceptable: SQL Editor is an internal admin tool.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. public.organizations trigger function
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
    -- Resolve actor
    BEGIN
        _actor_id := current_setting('app.acting_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        _actor_id := NULL;
    END;
    IF _actor_id IS NULL THEN _actor_id := auth.uid(); END IF;

    -- Skip when actor cannot be resolved. Python backend logs admin-client
    -- operations explicitly with full actor context.
    IF _actor_id IS NULL THEN RETURN NULL; END IF;

    SELECT email INTO _actor_email FROM public.profiles WHERE id = _actor_id;

    IF TG_OP = 'INSERT' THEN
        _action      := 'ORG_CREATED';
        _resource_id := NEW.id;
        _org_id      := NEW.id;
        _metadata    := jsonb_build_object('name', NEW.name, 'slug', NEW.slug, 'type', NEW.type);
    ELSIF TG_OP = 'UPDATE' THEN
        _action      := 'ORG_UPDATED';
        _resource_id := NEW.id;
        _org_id      := NEW.id;
        _metadata    := jsonb_build_object('name', NEW.name, 'slug', NEW.slug, 'type', NEW.type);
    ELSE
        _action      := 'ORG_DELETED';
        _resource_id := OLD.id;
        _org_id      := OLD.id;
        _metadata    := jsonb_build_object('name', OLD.name, 'slug', OLD.slug, 'type', OLD.type);
    END IF;

    PERFORM audit.log_change(
        'org', _action, 'organizations', _resource_id, _org_id,
        _actor_id, _actor_email, _metadata
    );

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, audit;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. public.organization_members trigger function
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

    IF _actor_id IS NULL THEN RETURN NULL; END IF;

    SELECT email INTO _actor_email FROM public.profiles WHERE id = _actor_id;

    IF TG_OP = 'INSERT' THEN
        _action      := 'MEMBER_ADDED';
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object('user_id', NEW.user_id, 'role', NEW.role, 'status', NEW.status);
    ELSIF TG_OP = 'UPDATE' THEN
        _action      := 'MEMBER_UPDATED';
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object(
            'user_id', NEW.user_id, 'role', NEW.role, 'old_role', OLD.role,
            'status', NEW.status, 'old_status', OLD.status
        );
    ELSE
        _action      := 'MEMBER_REMOVED';
        _resource_id := OLD.id;
        _org_id      := OLD.organization_id;
        _metadata    := jsonb_build_object('user_id', OLD.user_id, 'role', OLD.role, 'status', OLD.status);
    END IF;

    PERFORM audit.log_change(
        'org', _action, 'organization_members', _resource_id, _org_id,
        _actor_id, _actor_email, _metadata
    );

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, audit;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. crm.org_events trigger function
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

    IF _actor_id IS NULL THEN RETURN NULL; END IF;

    SELECT email INTO _actor_email FROM public.profiles WHERE id = _actor_id;

    IF TG_OP = 'INSERT' THEN
        _action      := 'EVENT_CREATED';
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object('name', NEW.name, 'slug', NEW.slug, 'status', NEW.status);
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.status IS DISTINCT FROM NEW.status THEN
            _action := 'EVENT_STATUS_CHANGED';
        ELSE
            _action := 'EVENT_UPDATED';
        END IF;
        _resource_id := NEW.id;
        _org_id      := NEW.organization_id;
        _metadata    := jsonb_build_object(
            'name', NEW.name, 'slug', NEW.slug, 'status', NEW.status, 'old_status', OLD.status
        );
    ELSE
        _action      := 'EVENT_DELETED';
        _resource_id := OLD.id;
        _org_id      := OLD.organization_id;
        _metadata    := jsonb_build_object('name', OLD.name, 'slug', OLD.slug, 'status', OLD.status);
    END IF;

    PERFORM audit.log_change(
        'event', _action, 'org_events', _resource_id, _org_id,
        _actor_id, _actor_email, _metadata
    );

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, audit, crm;

-- =============================================================================
-- DONE — Triggers replaced (no need to recreate: same name/table/event)
-- =============================================================================
SELECT '✅ MIGRATION: audit triggers updated — skip unknown actor' AS result;
