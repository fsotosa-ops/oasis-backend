-- Migration: Add category column to journeys.journeys
-- This supports categorizing journeys (e.g. 'onboarding', 'training', etc.)

ALTER TABLE journeys.journeys
  ADD COLUMN IF NOT EXISTS category TEXT;
