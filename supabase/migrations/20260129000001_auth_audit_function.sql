-- =============================================================================
-- MIGRATION: Auth Audit Functions
-- =============================================================================
-- Functions to log authentication events from the frontend.
-- These are called via Supabase RPC after successful auth operations.
-- =============================================================================

-- =============================================================================
-- 1. LOG AUTH EVENT (Called from frontend)
-- =============================================================================
CREATE OR REPLACE FUNCTION public.log_auth_event(
    p_action TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, audit
AS $$
DECLARE
    v_user_id UUID;
    v_user_email TEXT;
    v_log_id UUID;
BEGIN
    -- Get current user
    v_user_id := auth.uid();

    IF v_user_id IS NULL THEN
        RETURN NULL; -- No user context, skip logging
    END IF;

    -- Get user email from profiles
    SELECT email INTO v_user_email
    FROM public.profiles
    WHERE id = v_user_id;

    -- Insert audit log
    INSERT INTO audit.logs (
        actor_id,
        actor_email,
        category_code,
        action,
        resource,
        resource_id,
        metadata,
        ip_address,
        user_agent
    ) VALUES (
        v_user_id,
        v_user_email,
        'auth',
        p_action,
        'session',
        v_user_id,
        p_metadata,
        NULL, -- IP not available from RPC
        p_metadata->>'user_agent'
    )
    RETURNING id INTO v_log_id;

    RETURN v_log_id;
END;
$$;

-- Grant execute to authenticated users
GRANT EXECUTE ON FUNCTION public.log_auth_event(TEXT, JSONB) TO authenticated;

-- =============================================================================
-- 2. LOG LOGIN EVENT (With provider info)
-- =============================================================================
CREATE OR REPLACE FUNCTION public.log_login(
    p_provider TEXT DEFAULT 'email',
    p_user_agent TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, audit
AS $$
BEGIN
    RETURN public.log_auth_event(
        'LOGIN',
        jsonb_build_object(
            'provider', p_provider,
            'user_agent', p_user_agent,
            'timestamp', NOW()
        )
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.log_login(TEXT, TEXT) TO authenticated;

-- =============================================================================
-- 3. LOG LOGOUT EVENT
-- =============================================================================
CREATE OR REPLACE FUNCTION public.log_logout()
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, audit
AS $$
BEGIN
    RETURN public.log_auth_event(
        'LOGOUT',
        jsonb_build_object('timestamp', NOW())
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.log_logout() TO authenticated;

-- =============================================================================
-- 4. LOG REGISTER EVENT (Called after profile creation)
-- =============================================================================
-- Note: This is automatically triggered by handle_new_user, but we add
-- an explicit function for the audit log.

CREATE OR REPLACE FUNCTION public.log_register(
    p_provider TEXT DEFAULT 'email'
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, audit
AS $$
BEGIN
    RETURN public.log_auth_event(
        'REGISTER',
        jsonb_build_object(
            'provider', p_provider,
            'timestamp', NOW()
        )
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.log_register(TEXT) TO authenticated;

-- =============================================================================
-- DONE
-- =============================================================================
COMMENT ON FUNCTION public.log_auth_event IS 'Generic auth event logger for audit trail';
COMMENT ON FUNCTION public.log_login IS 'Log user login event';
COMMENT ON FUNCTION public.log_logout IS 'Log user logout event';
COMMENT ON FUNCTION public.log_register IS 'Log user registration event';
