-- Migration: Refactor org_type ENUM
-- Remove 'enterprise', keep 'community', 'provider', 'sponsor'
-- Existing orgs with type='enterprise' are migrated to 'provider'

-- Step 1: Create new enum without 'enterprise'
CREATE TYPE org_type_new AS ENUM ('community', 'provider', 'sponsor');

-- Step 2: Drop the DEFAULT before altering the type (Postgres cannot auto-cast defaults)
ALTER TABLE public.organizations ALTER COLUMN type DROP DEFAULT;

-- Step 3: Alter the column using CASE to migrate 'enterprise' → 'provider'
ALTER TABLE public.organizations
    ALTER COLUMN type TYPE org_type_new
    USING (
        CASE
            WHEN type::text = 'enterprise' THEN 'provider'::org_type_new
            ELSE type::text::org_type_new
        END
    );

-- Step 4: Drop the old type and rename the new one
DROP TYPE org_type;
ALTER TYPE org_type_new RENAME TO org_type;

-- Step 5: Re-add the DEFAULT with the renamed type
ALTER TABLE public.organizations ALTER COLUMN type SET DEFAULT 'provider'::org_type;
