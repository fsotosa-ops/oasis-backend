-- =============================================================================
-- Backfill crm.contacts for users created BEFORE the trigger
-- trg_auto_create_crm_contact (migration 20260211000002) existed.
-- Idempotent — ON CONFLICT DO NOTHING.
-- =============================================================================

INSERT INTO crm.contacts (user_id, email, first_name, last_name, avatar_url)
SELECT
    au.id,
    au.email,
    au.raw_user_meta_data ->> 'first_name',
    au.raw_user_meta_data ->> 'last_name',
    au.raw_user_meta_data ->> 'avatar_url'
FROM auth.users au
WHERE NOT EXISTS (SELECT 1 FROM crm.contacts c WHERE c.user_id = au.id)
  AND au.email IS NOT NULL
ON CONFLICT (user_id) DO NOTHING;
