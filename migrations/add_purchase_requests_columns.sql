-- Migration: add the columns the payment flow writes to `purchase_requests`.
-- Run ONCE in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Safe to re-run (IF NOT EXISTS).
--
-- Fixes the 500 / PGRST204 error when a user submits a payment receipt on /pay:
-- the insert writes `email` and `renew_sub_id`, which were missing from the table.

ALTER TABLE public.purchase_requests ADD COLUMN IF NOT EXISTS email        TEXT;
ALTER TABLE public.purchase_requests ADD COLUMN IF NOT EXISTS renew_sub_id TEXT;
ALTER TABLE public.purchase_requests ADD COLUMN IF NOT EXISTS price        TEXT;

NOTIFY pgrst, 'reload schema';
