-- Migration: Auto-create crm.organization_profiles on org creation
-- Mirrors the pattern of trg_auto_create_crm_contact for contacts.

CREATE OR REPLACE FUNCTION crm.auto_create_org_profile()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    INSERT INTO crm.organization_profiles (org_id)
    VALUES (NEW.id)
    ON CONFLICT (org_id) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_auto_create_org_profile
    AFTER INSERT ON public.organizations
    FOR EACH ROW EXECUTE FUNCTION crm.auto_create_org_profile();

-- Backfill existing orgs that don't have a profile yet
INSERT INTO crm.organization_profiles (org_id)
SELECT id FROM public.organizations
WHERE id NOT IN (SELECT org_id FROM crm.organization_profiles)
ON CONFLICT (org_id) DO NOTHING;
