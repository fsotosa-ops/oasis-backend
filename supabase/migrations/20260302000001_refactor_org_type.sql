-- Migration: Refactor org_type ENUM (idempotent / safe to re-run)
-- Remove 'enterprise', keep 'community', 'provider', 'sponsor'
-- Existing orgs with type='enterprise' are migrated to 'provider'

-- ─── Step 1: Drop ALL policies that reference organizations.type ──────────────
-- Postgres raises 0A000 if ANY policy references the column being altered,
-- including cross-table references (e.g. subqueries in organization_members).

-- Direct references on public.organizations
DROP POLICY IF EXISTS "organizations_select_community" ON public.organizations;
DROP POLICY IF EXISTS "organizations_delete_admin"     ON public.organizations;

-- Cross-table reference: members_delete subquery uses organizations.type
DROP POLICY IF EXISTS "members_delete" ON public.organization_members;

-- ─── Step 2: Drop the column DEFAULT (required before type change) ────────────
ALTER TABLE public.organizations ALTER COLUMN type DROP DEFAULT;

-- ─── Step 3: Convert column to text (safe intermediate step) ─────────────────
ALTER TABLE public.organizations ALTER COLUMN type TYPE text;

-- ─── Step 4: Drop old enum(s) (column no longer references them) ─────────────
DROP TYPE IF EXISTS org_type;
DROP TYPE IF EXISTS org_type_new;  -- in case of previous partial execution

-- ─── Step 5: Migrate stale data ───────────────────────────────────────────────
UPDATE public.organizations SET type = 'provider' WHERE type = 'enterprise';

-- ─── Step 6: Create the clean new enum ───────────────────────────────────────
CREATE TYPE org_type AS ENUM ('community', 'provider', 'sponsor');

-- ─── Step 7: Convert column from text back to enum ───────────────────────────
ALTER TABLE public.organizations
    ALTER COLUMN type TYPE org_type
    USING type::org_type;

-- ─── Step 8: Restore column DEFAULT ──────────────────────────────────────────
ALTER TABLE public.organizations ALTER COLUMN type SET DEFAULT 'community'::org_type;

-- ─── Step 9: Recreate all dropped policies ────────────────────────────────────

CREATE POLICY "organizations_select_community" ON public.organizations
    FOR SELECT USING (type = 'community');

CREATE POLICY "organizations_delete_admin" ON public.organizations
    FOR DELETE USING (
        public.is_platform_admin() = TRUE
        AND type != 'community'
    );

CREATE POLICY "members_delete" ON public.organization_members
    FOR DELETE USING (
        -- Self-removal (user leaving an org, except community)
        (
            user_id = auth.uid()
            AND NOT EXISTS (
                SELECT 1 FROM public.organizations
                WHERE id = organization_id AND type = 'community'
            )
        )
        -- Org admin removing someone
        OR public.is_org_admin(organization_id) = TRUE
        -- Platform admin
        OR public.is_platform_admin() = TRUE
    );
