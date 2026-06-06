from cachetools import cached, TTLCache
from supabase_client import supabase_admin

# إنشاء الكاش بمدة 60 ثانية (TTL = 60)
users_ttl = TTLCache(maxsize=1, ttl=60)
servers_ttl = TTLCache(maxsize=1, ttl=60)
messages_ttl = TTLCache(maxsize=1, ttl=60)
subscriptions_ttl = TTLCache(maxsize=1, ttl=60)
pricing_rules_ttl = TTLCache(maxsize=1, ttl=60)
source_links_ttl = TTLCache(maxsize=1, ttl=60)

@cached(cache=users_ttl)
def get_all_users():
    response = supabase_admin.table('users').select('*').execute()
    return {doc['id']: doc for doc in response.data} if response.data else {}

@cached(cache=servers_ttl)
def get_all_servers():
    response = supabase_admin.table('servers').select('*').execute()
    return {doc['id']: doc for doc in response.data} if response.data else {}

@cached(cache=messages_ttl)
def get_all_messages():
    response = supabase_admin.table('messages').select('*').execute()
    return {doc['id']: doc for doc in response.data} if response.data else {}

@cached(cache=subscriptions_ttl)
def get_all_subscriptions():
    response = supabase_admin.table('subscriptions').select('*').execute()
    return {doc['id']: doc for doc in response.data} if response.data else {}

@cached(cache=pricing_rules_ttl)
def get_all_pricing_rules():
    response = supabase_admin.table('pricing_rules').select('*').execute()
    return {doc['id']: doc for doc in response.data} if response.data else {}

@cached(cache=source_links_ttl)
def get_all_source_links():
    response = supabase_admin.table('source_links').select('*').execute()
    return {doc['id']: doc for doc in response.data} if response.data else {}


# --- Cache invalidation -------------------------------------------------
# Call these right after a write so the next read returns fresh data instead
# of waiting up to 60s for the TTL to expire (otherwise newly added items
# appear to "take a long time" to show up in the admin dashboard).
def invalidate_users():
    users_ttl.clear()

def invalidate_servers():
    servers_ttl.clear()

def invalidate_messages():
    messages_ttl.clear()

def invalidate_subscriptions():
    subscriptions_ttl.clear()

def invalidate_pricing_rules():
    pricing_rules_ttl.clear()

def invalidate_source_links():
    source_links_ttl.clear()
