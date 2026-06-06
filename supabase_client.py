import os
from dotenv import load_dotenv
from supabase import create_client, Client
import httpx

# Monkey-patch httpx to ignore proxies (Windows registry socks4 issue)
original_init = httpx.Client.__init__
def patched_init(self, *args, **kwargs):
    kwargs['trust_env'] = False
    kwargs['proxy'] = None
    original_init(self, *args, **kwargs)
httpx.Client.__init__ = patched_init

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Public client (uses anon key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Admin client (uses service_role key - bypasses RLS)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None
