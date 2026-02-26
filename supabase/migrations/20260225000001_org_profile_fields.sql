-- Migration: Add CRM profile fields to organizations table
-- Date: 2026-02-25

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS website TEXT,
  ADD COLUMN IF NOT EXISTS phone TEXT,
  ADD COLUMN IF NOT EXISTS industry TEXT,
  ADD COLUMN IF NOT EXISTS company_size TEXT,
  ADD COLUMN IF NOT EXISTS address TEXT;
