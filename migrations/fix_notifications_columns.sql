-- Migration: make the `notifications` table match what the code writes/reads.
-- Run ONCE in the Supabase SQL Editor. Safe to re-run (IF NOT EXISTS).
--
-- The code inserts notifications with `title`, `message`, `type`, `is_read`,
-- `created_at` and the admin bell counts `is_read = false`. An older schema
-- used `read` with no `title`, so the bell/notifications silently broke.

ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS title      TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS message    TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS type       TEXT DEFAULT 'info';
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS is_read    BOOLEAN DEFAULT FALSE;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS user_id    TEXT;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

NOTIFY pgrst, 'reload schema';
