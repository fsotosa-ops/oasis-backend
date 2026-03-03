-- Migration: Sync first_name/last_name in crm.contacts from auth.profiles.full_name
-- Fixes: contacts created without copying name from profiles

-- 1. Función trigger: auto-poblar first_name/last_name desde profiles
CREATE OR REPLACE FUNCTION crm.sync_name_from_profile()
RETURNS TRIGGER AS $$
DECLARE
  v_full_name TEXT;
  v_space_pos INT;
BEGIN
  -- Solo actúa si alguno de los campos está vacío
  IF NEW.first_name IS NULL OR NEW.last_name IS NULL THEN
    SELECT full_name INTO v_full_name
    FROM public.profiles WHERE id = NEW.user_id;

    IF v_full_name IS NOT NULL THEN
      v_space_pos := position(' ' IN trim(v_full_name));
      IF v_space_pos > 0 THEN
        NEW.first_name := COALESCE(NEW.first_name, trim(split_part(v_full_name, ' ', 1)));
        NEW.last_name  := COALESCE(NEW.last_name,  trim(substring(v_full_name FROM v_space_pos + 1)));
      ELSE
        NEW.first_name := COALESCE(NEW.first_name, trim(v_full_name));
        -- last_name se deja NULL si el nombre es una sola palabra
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Trigger BEFORE INSERT OR UPDATE en crm.contacts
DROP TRIGGER IF EXISTS crm_contacts_sync_name ON crm.contacts;
CREATE TRIGGER crm_contacts_sync_name
  BEFORE INSERT OR UPDATE ON crm.contacts
  FOR EACH ROW EXECUTE FUNCTION crm.sync_name_from_profile();

-- 3. UPDATE retroactivo para registros existentes con nombres nulos
UPDATE crm.contacts c
SET
  first_name = CASE
    WHEN position(' ' IN trim(p.full_name)) > 0
    THEN trim(split_part(p.full_name, ' ', 1))
    ELSE trim(p.full_name)
  END,
  last_name = CASE
    WHEN position(' ' IN trim(p.full_name)) > 0
    THEN trim(substring(p.full_name FROM position(' ' IN trim(p.full_name)) + 1))
    ELSE NULL
  END
FROM public.profiles p
WHERE c.user_id = p.id
  AND (c.first_name IS NULL OR c.last_name IS NULL)
  AND p.full_name IS NOT NULL
  AND trim(p.full_name) <> '';
