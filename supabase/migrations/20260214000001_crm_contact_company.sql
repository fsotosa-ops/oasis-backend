-- Add company field to CRM contacts
ALTER TABLE crm.contacts ADD COLUMN IF NOT EXISTS company TEXT;
