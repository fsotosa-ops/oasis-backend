-- Migration: Fix org_events missing columns
-- The table was created from an older version of migration 0002 before
-- several columns were added. This is a safe, idempotent ALTER to bring
-- any existing table up to the current expected schema.

-- 1. Add notes and expected_participants (added in a later revision of 0002)
ALTER TABLE crm.org_events
    ADD COLUMN IF NOT EXISTS notes                 TEXT,
    ADD COLUMN IF NOT EXISTS expected_participants INTEGER;

-- 2. Handle journey_id (UUID, singular) → journey_ids (UUID[], plural)
--    Only runs if the old column still exists.
DO $$
BEGIN
    -- Add journey_ids array if it doesn't exist yet
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'crm'
          AND table_name   = 'org_events'
          AND column_name  = 'journey_ids'
    ) THEN
        ALTER TABLE crm.org_events
            ADD COLUMN journey_ids UUID[] NOT NULL DEFAULT '{}';
    END IF;

    -- Migrate data from journey_id → journey_ids and drop the old column
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'crm'
          AND table_name   = 'org_events'
          AND column_name  = 'journey_id'
    ) THEN
        UPDATE crm.org_events
        SET    journey_ids = ARRAY[journey_id]
        WHERE  journey_id IS NOT NULL
          AND  (journey_ids IS NULL OR journey_ids = '{}');

        ALTER TABLE crm.org_events DROP COLUMN journey_id;
    END IF;
END $$;

-- 3. Backfill landing_config with new keys for rows that were saved before
--    background_end_color / gradient_direction / text_color were added.
UPDATE crm.org_events
SET landing_config = '{
    "title": null,
    "welcome_message": null,
    "primary_color": "#3B82F6",
    "background_color": "#0F172A",
    "background_end_color": null,
    "gradient_direction": "to-b",
    "background_image_url": null,
    "text_color": "#FFFFFF",
    "show_qr": true,
    "custom_logo_url": null
}'::jsonb || landing_config
WHERE NOT (landing_config ? 'text_color');
