-- =============================================================================
-- MIGRATION: Fix infinite recursion in profiles UPDATE RLS policy
-- DATE: 2026-02-20
-- FIX: "infinite recursion detected in policy for relation 'profiles'"
--
-- The profiles_update_own policy had an inline subquery on the profiles table
-- inside its WITH CHECK clause:
--
--   WITH CHECK (
--     id = auth.uid()
--     AND is_platform_admin = (SELECT is_platform_admin FROM profiles WHERE id = auth.uid())
--   )
--
-- PostgreSQL detects this self-reference at plan time and raises error 42P17.
--
-- Fix: replace the inline subquery with the existing is_platform_admin()
-- SECURITY DEFINER function, which is opaque to the planner and runs as
-- postgres (BYPASSRLS) at execution time.
-- =============================================================================

DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;

CREATE POLICY "profiles_update_own" ON public.profiles
FOR UPDATE
USING (id = auth.uid())
WITH CHECK (
    id = auth.uid()
    AND is_platform_admin IS NOT DISTINCT FROM public.is_platform_admin()
);
