from cachetools import cached, TTLCache
from extensions import db

# إنشاء الكاش بمدة 60 ثانية (TTL = 60)
users_ttl = TTLCache(maxsize=1, ttl=60)
servers_ttl = TTLCache(maxsize=1, ttl=60)
messages_ttl = TTLCache(maxsize=1, ttl=60)
subscriptions_ttl = TTLCache(maxsize=1, ttl=60)
pricing_rules_ttl = TTLCache(maxsize=1, ttl=60)
source_links_ttl = TTLCache(maxsize=1, ttl=60)

@cached(cache=users_ttl)
def get_all_users():
    docs = db.collection('users').stream()
    return {doc.id: doc.to_dict() for doc in docs}

@cached(cache=servers_ttl)
def get_all_servers():
    docs = db.collection('servers').stream()
    return {doc.id: doc.to_dict() for doc in docs}

@cached(cache=messages_ttl)
def get_all_messages():
    docs = db.collection('messages').stream()
    return {doc.id: doc.to_dict() for doc in docs}

@cached(cache=subscriptions_ttl)
def get_all_subscriptions():
    docs = db.collection('subscriptions').stream()
    return {doc.id: doc.to_dict() for doc in docs}

@cached(cache=pricing_rules_ttl)
def get_all_pricing_rules():
    docs = db.collection('pricing_rules').stream()
    return {doc.id: doc.to_dict() for doc in docs}

@cached(cache=source_links_ttl)
def get_all_source_links():
    docs = db.collection('source_links').stream()
    return {doc.id: doc.to_dict() for doc in docs}
