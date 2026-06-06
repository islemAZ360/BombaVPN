-- Migration: add the columns the import/sync code writes to the `servers` table.
-- Run this ONCE in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
-- Safe to re-run: every statement uses IF NOT EXISTS.
--
-- Fixes: PGRST204 "Could not find the 'country_code' column of 'servers'
-- in the schema cache" (and the other missing columns) when importing
-- VLESS servers via Auto Import or syncing a provider subscription link.

ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS source_link_id     TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS original_ip        TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS country_code       TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS json_config        TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS vless_link         TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS price              NUMERIC DEFAULT 0;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS total_plan_seconds BIGINT  DEFAULT 0;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS expires_at         TIMESTAMP WITH TIME ZONE;

-- Tell PostgREST (the Supabase REST layer) to refresh its schema cache so the
-- new columns are visible immediately without waiting for an auto-reload.
NOTIFY pgrst, 'reload schema';
