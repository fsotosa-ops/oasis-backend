-- ============================================================
-- Migration: Auto-log field changes on crm.contacts
-- A Postgres trigger that captures every UPDATE to tracked
-- profile fields and inserts rows into crm.contact_changes.
--
-- This is the "safety net" layer — it catches ALL changes
-- regardless of origin (API, admin console, SQL direct).
-- The application layer supplements with changed_by.
-- ============================================================

-- Tracked fields for changelog
CREATE OR REPLACE FUNCTION crm.log_contact_field_changes()
RETURNS TRIGGER AS $$
DECLARE
    _fields TEXT[] := ARRAY[
        'first_name', 'last_name', 'phone',
        'country', 'state', 'city',
        'birth_date', 'gender', 'education_level', 'occupation',
        'status'
    ];
    _field TEXT;
    _old TEXT;
    _new TEXT;
    _changed_by UUID;
BEGIN
    -- Try to get the acting user: first from app context, then from auth
    BEGIN
        _changed_by := current_setting('app.acting_user_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        _changed_by := NULL;
    END;

    IF _changed_by IS NULL THEN
        _changed_by := auth.uid();
    END IF;

    FOREACH _field IN ARRAY _fields LOOP
        -- Use hstore-style dynamic comparison via to_jsonb
        _old := (to_jsonb(OLD) ->> _field);
        _new := (to_jsonb(NEW) ->> _field);

        -- Only log if value actually changed (handles NULL correctly)
        IF _old IS DISTINCT FROM _new THEN
            INSERT INTO crm.contact_changes (
                contact_user_id,
                changed_by,
                change_type,
                field_name,
                old_value,
                new_value
            ) VALUES (
                NEW.user_id,
                _changed_by,
                'field_update',
                _field,
                _old,
                _new
            );
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fire AFTER UPDATE so we don't block the write
CREATE TRIGGER trg_log_contact_field_changes
    AFTER UPDATE ON crm.contacts
    FOR EACH ROW
    EXECUTE FUNCTION crm.log_contact_field_changes();