-- Migration: CRM Organization Profiles
-- Date: 2026-02-25
-- Creates crm.organization_profiles to enrich public.organizations with CRM-specific data,
-- following the same pattern as crm.contacts enriching auth.users.

CREATE TABLE IF NOT EXISTS crm.organization_profiles (
    org_id      UUID PRIMARY KEY REFERENCES public.organizations(id) ON DELETE CASCADE,
    website     TEXT,
    phone       TEXT,
    industry    TEXT,
    company_size TEXT,
    address     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at
CREATE TRIGGER update_crm_org_profiles_modtime
    BEFORE UPDATE ON crm.organization_profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Enable RLS
ALTER TABLE crm.organization_profiles ENABLE ROW LEVEL SECURITY;

-- Platform admins manage all org profiles
CREATE POLICY "Platform Admins manage all org profiles" ON crm.organization_profiles
    FOR ALL USING (crm.is_platform_admin());

-- Org members can read their org's profile
CREATE POLICY "Org Members read their org profile" ON crm.organization_profiles
    FOR SELECT USING (crm.is_org_member(org_id));

-- Org admins/owners can write their org's profile
CREATE POLICY "Org Admins write their org profile" ON crm.organization_profiles
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.organization_members
            WHERE user_id = auth.uid()
              AND organization_id = org_id
              AND status = 'active'
              AND role IN ('owner', 'admin')
        )
    );
