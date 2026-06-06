-- SQL Schema for GalaxyVPN Migration

-- 1. Users Table
CREATE TABLE IF NOT EXISTS public.users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    referral_code TEXT UNIQUE,
    referred_by TEXT,
    accessed_ips JSONB DEFAULT '[]'::jsonb,
    accessed_devices JSONB DEFAULT '[]'::jsonb,
    is_renewal BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending',
    latest_req_status TEXT,
    latest_req JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Servers Table
CREATE TABLE IF NOT EXISTS public.servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    group_name TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    monthly_price NUMERIC,
    domain TEXT,
    type TEXT,
    subdomain_offset INTEGER DEFAULT 0,
    subdomain_limit INTEGER DEFAULT 100,
    assigned_subdomains JSONB DEFAULT '[]'::jsonb,
    plan_days INTEGER DEFAULT 0,
    plan_hours INTEGER DEFAULT 0,
    plan_minutes INTEGER DEFAULT 0,
    -- Columns used by the VLESS import / sync flow
    source_link_id TEXT,
    original_ip TEXT,
    country_code TEXT,
    json_config TEXT,
    vless_link TEXT,
    price NUMERIC DEFAULT 0,
    total_plan_seconds BIGINT DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- For existing databases created before the import columns were added,
-- bring the table up to date (safe to re-run):
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS source_link_id     TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS original_ip        TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS country_code       TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS json_config        TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS vless_link         TEXT;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS price              NUMERIC DEFAULT 0;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS total_plan_seconds BIGINT  DEFAULT 0;
ALTER TABLE public.servers ADD COLUMN IF NOT EXISTS expires_at         TIMESTAMP WITH TIME ZONE;

-- 3. Subscriptions Table
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES public.users(id) ON DELETE CASCADE,
    server_id TEXT REFERENCES public.servers(id) ON DELETE SET NULL,
    allocated_subdomain TEXT,
    status TEXT DEFAULT 'active',
    is_temporary BOOLEAN DEFAULT FALSE,
    original_server_id TEXT,
    required_tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

-- 4. Payments Table
CREATE TABLE IF NOT EXISTS public.payments (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES public.users(id) ON DELETE CASCADE,
    server_id TEXT REFERENCES public.servers(id) ON DELETE SET NULL,
    amount NUMERIC,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'completed',
    telegram_message_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Notifications Table
CREATE TABLE IF NOT EXISTS public.notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES public.users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    type TEXT DEFAULT 'info',
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Debts Table
CREATE TABLE IF NOT EXISTS public.debts (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    amount NUMERIC DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security (RLS) but allow Service Role full access
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.servers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debts ENABLE ROW LEVEL SECURITY;

-- Create Policies to allow Anon read/write (temporarily or handled by Python Backend)
-- Since the Python backend uses the Service Role key, it bypasses RLS automatically.
-- We will allow public read access for servers so the frontend can display them.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'servers' AND policyname = 'Allow public read access for servers'
    ) THEN
        CREATE POLICY "Allow public read access for servers" ON public.servers FOR SELECT USING (true);
    END IF;
END
$$;

-- Create messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    message TEXT,
    image TEXT,
    email TEXT,
    admin_reply TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_read BOOLEAN DEFAULT FALSE,
    reply_to UUID,
    is_admin_reply BOOLEAN DEFAULT FALSE
);

-- Create purchase_requests table
CREATE TABLE IF NOT EXISTS purchase_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    server_id TEXT REFERENCES servers(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending',
    receipt_url TEXT,
    price TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Note: admin_messages was originally a subcollection in Firestore. In SQL, we can just use the messages table with is_admin_reply=true.

-- Create admin_messages table
CREATE TABLE IF NOT EXISTS admin_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    message TEXT,
    image TEXT,
    email TEXT,
    admin_reply TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_read BOOLEAN DEFAULT FALSE
);

-- Create notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT,
    message TEXT,
    type TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Pricing Rules Table
CREATE TABLE IF NOT EXISTS public.pricing_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tags JSONB DEFAULT '[]'::jsonb,
    duration_days INTEGER DEFAULT 0,
    total_duration_seconds INTEGER DEFAULT 0,
    price NUMERIC DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Source Links Table
CREATE TABLE IF NOT EXISTS public.source_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT,
    total_plan_seconds INTEGER DEFAULT 0,
    total_real_seconds INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
