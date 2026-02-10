-- =============================================================================
-- MIGRATION: CRM Module Schema & Security Policies
-- DATE: 2026-02-11
-- DESCRIPTION: Implementation of multi-tenant CRM with hybrid scope (Global/Org)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS crm;

-- 1. Global Contacts Table (One record per user, shared across orgs)
-- Stores objective data: Identity, Demographics, Contact Info.
CREATE TABLE crm.contacts (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    country TEXT,
    avatar_url TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'risk')),
    
    -- Calculated/Denormalized fields for performance
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Organization Notes (Scoped per Org)
-- Subjective data: "User is a community leader" (Context: Org A)
CREATE TABLE crm.notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_user_id UUID NOT NULL REFERENCES crm.contacts(user_id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    author_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Organization Tasks (Scoped per Org)
-- Actionable items: "Call Juan" (Context: Org A)
CREATE TABLE crm.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_user_id UUID NOT NULL REFERENCES crm.contacts(user_id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    
    created_by UUID REFERENCES auth.users(id),
    assigned_to UUID REFERENCES auth.users(id),
    
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    due_date TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE crm.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm.tasks ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- RLS HELPER FUNCTIONS
-- =============================================================================

-- Function to check if user is Platform Admin (Fundación Summer Admin)
CREATE OR REPLACE FUNCTION crm.is_platform_admin() 
RETURNS BOOLEAN AS $$
BEGIN
  -- Logic: User is 'is_platform_admin' in metadata OR Admin/Owner of 'Fundación Summer'
  RETURN (
    (auth.jwt() -> 'user_metadata' ->> 'is_platform_admin')::boolean IS TRUE
    OR EXISTS (
      SELECT 1 FROM public.organization_members om
      JOIN public.organizations o ON om.organization_id = o.id
      WHERE om.user_id = auth.uid() 
      AND o.name = 'Fundación Summer' 
      AND om.role IN ('owner', 'admin')
    )
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to check if user is a Member of an Organization
CREATE OR REPLACE FUNCTION crm.is_org_member(org_id UUID) 
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.organization_members 
    WHERE user_id = auth.uid() 
    AND organization_id = org_id 
    AND status = 'active'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- RLS POLICIES
-- =============================================================================

-- CONTACTS POLICIES
-- 1. Platform Admins view ALL contacts.
CREATE POLICY "Platform Admins view all contacts" ON crm.contacts
FOR SELECT USING (crm.is_platform_admin());

-- 2. Org Admins/Members view contacts that belong to their organizations.
CREATE POLICY "Org Members view their contacts" ON crm.contacts
FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM public.organization_members om_viewer
        JOIN public.organization_members om_target ON om_viewer.organization_id = om_target.organization_id
        WHERE om_viewer.user_id = auth.uid()
        AND om_target.user_id = crm.contacts.user_id
        AND om_viewer.status = 'active'
    )
);

-- NOTES POLICIES
-- 1. Platform Admins view all notes.
CREATE POLICY "Platform Admins manage all notes" ON crm.notes
FOR ALL USING (crm.is_platform_admin());

-- 2. Users view/manage notes ONLY for their Organizations.
CREATE POLICY "Org Members manage their org notes" ON crm.notes
FOR ALL USING (
    crm.is_org_member(organization_id)
);

-- TASKS POLICIES
-- 1. Platform Admins view all tasks.
CREATE POLICY "Platform Admins manage all tasks" ON crm.tasks
FOR ALL USING (crm.is_platform_admin());

-- 2. Users view/manage tasks ONLY for their Organizations.
CREATE POLICY "Org Members manage their org tasks" ON crm.tasks
FOR ALL USING (
    crm.is_org_member(organization_id)
);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-update updated_at for CRM tables
CREATE TRIGGER update_crm_contacts_modtime BEFORE UPDATE ON crm.contacts
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_crm_notes_modtime BEFORE UPDATE ON crm.notes
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_crm_tasks_modtime BEFORE UPDATE ON crm.tasks
FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();