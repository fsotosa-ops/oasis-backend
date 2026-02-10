-- =============================================================================
-- MIGRATION: CRM Indexes, Missing Policies, Auto-Contact Trigger, Changelog
-- DATE: 2026-02-11
-- DESCRIPTION: Performance indexes, INSERT/UPDATE policies for contacts,
--   WITH CHECK on notes/tasks INSERT, auto-create contact trigger,
--   contact_changes changelog table.
-- =============================================================================

-- =============================================================================
-- 1. INDEXES (Performance)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_crm_notes_contact ON crm.notes(contact_user_id);
CREATE INDEX IF NOT EXISTS idx_crm_notes_org ON crm.notes(organization_id);
CREATE INDEX IF NOT EXISTS idx_crm_notes_author ON crm.notes(author_id);

CREATE INDEX IF NOT EXISTS idx_crm_tasks_contact ON crm.tasks(contact_user_id);
CREATE INDEX IF NOT EXISTS idx_crm_tasks_org ON crm.tasks(organization_id);
CREATE INDEX IF NOT EXISTS idx_crm_tasks_assigned ON crm.tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_crm_tasks_status ON crm.tasks(status);
CREATE INDEX IF NOT EXISTS idx_crm_tasks_due_date ON crm.tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_crm_tasks_created_by ON crm.tasks(created_by);

-- =============================================================================
-- 2. CONTACTS: Auto-create trigger (1:1 with auth.users)
-- =============================================================================

CREATE OR REPLACE FUNCTION crm.auto_create_contact()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO crm.contacts (user_id, email, first_name, last_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        NEW.raw_user_meta_data ->> 'first_name',
        NEW.raw_user_meta_data ->> 'last_name',
        NEW.raw_user_meta_data ->> 'avatar_url'
    )
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fire after a new user is created in auth.users
CREATE TRIGGER trg_auto_create_crm_contact
AFTER INSERT ON auth.users
FOR EACH ROW
EXECUTE FUNCTION crm.auto_create_contact();

-- =============================================================================
-- 3. CONTACTS: INSERT & UPDATE policies (missing in original migration)
-- =============================================================================

-- Platform admins can insert contacts (e.g. manual import)
CREATE POLICY "Platform Admins insert contacts" ON crm.contacts
FOR INSERT WITH CHECK (crm.is_platform_admin());

-- Platform admins can update any contact
CREATE POLICY "Platform Admins update contacts" ON crm.contacts
FOR UPDATE USING (crm.is_platform_admin());

-- Org admins/members can update contacts that belong to their orgs
CREATE POLICY "Org Members update their contacts" ON crm.contacts
FOR UPDATE USING (
    EXISTS (
        SELECT 1 FROM public.organization_members om_viewer
        JOIN public.organization_members om_target
            ON om_viewer.organization_id = om_target.organization_id
        WHERE om_viewer.user_id = auth.uid()
        AND om_target.user_id = crm.contacts.user_id
        AND om_viewer.status = 'active'
        AND om_viewer.role IN ('owner', 'admin')
    )
);

-- =============================================================================
-- 4. NOTES & TASKS: Add WITH CHECK to INSERT policies
-- The existing FOR ALL policies have USING but no WITH CHECK for INSERT,
-- which means INSERT defaults to the USING clause. We add explicit INSERT
-- policies with WITH CHECK to validate organization_id ownership.
-- =============================================================================

-- Notes: org members can only insert notes for their own orgs
CREATE POLICY "Org Members insert notes for their org" ON crm.notes
FOR INSERT WITH CHECK (
    crm.is_org_member(organization_id)
);

-- Tasks: org members can only insert tasks for their own orgs
CREATE POLICY "Org Members insert tasks for their org" ON crm.tasks
FOR INSERT WITH CHECK (
    crm.is_org_member(organization_id)
);

-- Platform admins insert notes/tasks (already covered by FOR ALL, but explicit)
CREATE POLICY "Platform Admins insert notes" ON crm.notes
FOR INSERT WITH CHECK (crm.is_platform_admin());

CREATE POLICY "Platform Admins insert tasks" ON crm.tasks
FOR INSERT WITH CHECK (crm.is_platform_admin());

-- =============================================================================
-- 5. CONTACT_CHANGES: Changelog table for audit trail
-- =============================================================================

CREATE TABLE crm.contact_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_user_id UUID NOT NULL REFERENCES crm.contacts(user_id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    changed_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('status_change', 'field_update', 'note_added', 'task_created', 'task_completed')),
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_contact_changes_contact ON crm.contact_changes(contact_user_id);
CREATE INDEX IF NOT EXISTS idx_crm_contact_changes_org ON crm.contact_changes(organization_id);
CREATE INDEX IF NOT EXISTS idx_crm_contact_changes_type ON crm.contact_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_crm_contact_changes_created ON crm.contact_changes(created_at);

ALTER TABLE crm.contact_changes ENABLE ROW LEVEL SECURITY;

-- Platform admins see all changes
CREATE POLICY "Platform Admins manage all contact_changes" ON crm.contact_changes
FOR ALL USING (crm.is_platform_admin());

-- Org members see changes for their org
CREATE POLICY "Org Members view their org contact_changes" ON crm.contact_changes
FOR SELECT USING (
    crm.is_org_member(organization_id)
);

-- Org members can insert changes for their org
CREATE POLICY "Org Members insert contact_changes for their org" ON crm.contact_changes
FOR INSERT WITH CHECK (
    crm.is_org_member(organization_id)
);
