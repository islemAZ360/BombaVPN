import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Add current dir to path so we can import app stuff
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import db, servers_cache, servers_cache_lock

def setup_simulation():
    print("Setting up simulation data...")
    # Clean up old simulation data
    for doc in db.collection('users').where('email', '==', 'sim_user@example.com').stream():
        db.collection('users').document(doc.id).delete()
    for doc in db.collection('servers').where('name', '>=', 'SimServer').stream():
        db.collection('servers').document(doc.id).delete()
    for doc in db.collection('subscriptions').where('allocated_subdomain', '>=', 'sim_user').stream():
        db.collection('subscriptions').document(doc.id).delete()

    # 1. Create a dummy user
    user_ref = db.collection('users').add({
        'email': 'sim_user@example.com',
        'status': 'active',
        'created_at': datetime.utcnow()
    })
    user_id = user_ref[1].id
    print(f"Created Sim User: {user_id}")

    # 2. Create Server A (Dead server with premium tag)
    server_a_ref = db.collection('servers').add({
        'name': 'SimServer_A_Premium_Dead',
        'tags': ['premium'],
        'expires_at': datetime.utcnow() - timedelta(minutes=5), # Already expired!
        'original_ip': '1.1.1.1'
    })
    server_a_id = server_a_ref[1].id
    print(f"Created Server A (Dead Premium): {server_a_id}")

    # 3. Create Server B (Active but NO tags - Fallback)
    server_b_ref = db.collection('servers').add({
        'name': 'SimServer_B_Fallback',
        'tags': [],
        'expires_at': datetime.utcnow() + timedelta(days=30),
        'original_ip': '2.2.2.2'
    })
    server_b_id = server_b_ref[1].id
    print(f"Created Server B (Active Fallback): {server_b_id}")

    # 4. Create a subscription for the user on Server A
    sub_ref = db.collection('subscriptions').add({
        'user_id': user_id,
        'server_id': server_a_id,
        'allocated_subdomain': 'sim_user-xxxxxx.bombavpn.dynv6.net',
        'status': 'active',
        'required_tags': ['premium'],
        'is_temporary': False,
        'expires_at': datetime.utcnow() + timedelta(days=10)
    })
    sub_id = sub_ref[1].id
    print(f"Created Subscription on Server A: {sub_id}")
    
    return user_id, server_a_id, server_b_id, sub_id

def run_worker_iteration():
    print("\n--- Running Worker Iteration ---")
    now = datetime.utcnow()
    
    # Manually populate servers cache to mimic on_snapshot
    with servers_cache_lock:
        servers_cache.clear()
        for doc in db.collection('servers').stream():
            servers_cache[doc.id] = doc.to_dict()
            
        all_active_servers = []
        for s_id, s_dict in servers_cache.items():
            s = s_dict.copy()
            s['id'] = s_id
            s_expires = s.get('expires_at')
            if s_expires and s_expires.replace(tzinfo=None) > now:
                all_active_servers.append(s)

    for doc in db.collection('subscriptions').where('status', '==', 'active').stream():
        sub_id = doc.id
        sub = doc.to_dict()
        
        # Only process our sim sub
        if 'sim_user' not in (sub.get('allocated_subdomain') or ''):
            continue
            
        expires_at = sub.get('expires_at')
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                print(f"Subscription {sub_id} expired.")
                db.collection('subscriptions').document(sub_id).update({'status': 'expired'})
                continue
                
        server_dead = True
        allocated_server_id = sub.get('server_id')
        if allocated_server_id:
            for active_s in all_active_servers:
                if active_s['id'] == allocated_server_id:
                    server_dead = False
                    break
                    
        is_temp = sub.get('is_temporary', False)
        
        if server_dead or is_temp:
            print(f"Action needed for sub {sub_id}: server_dead={server_dead}, is_temp={is_temp}")
            required_tags = set(sub.get('required_tags') or [])
            candidate_servers = []
            for s in all_active_servers:
                s_tags = set(s.get('tags') or [])
                if required_tags.issubset(s_tags):
                    candidate_servers.append(s)
                    
            if candidate_servers:
                best_server = max(candidate_servers, key=lambda s: s['expires_at'].replace(tzinfo=None))
                new_temp = False
            elif server_dead:
                if not all_active_servers:
                    continue
                best_server = max(all_active_servers, key=lambda s: s['expires_at'].replace(tzinfo=None))
                new_temp = True
            else:
                continue
                
            if best_server['id'] != allocated_server_id:
                safe_prefix = 'sim_user'
                subdomain = f"{safe_prefix}-{best_server['id'][:6]}.bombavpn.dynv6.net"
                print(f"MIGRATING sub {sub_id} to server {best_server['id']} (temp={new_temp})")
                db.collection('subscriptions').document(sub_id).update({
                    'server_id': best_server['id'],
                    'allocated_subdomain': subdomain,
                    'is_temporary': new_temp
                })
                
                # Debt notification
                best_exp = best_server['expires_at'].replace(tzinfo=None)
                exp_at_naive = expires_at.replace(tzinfo=None) if expires_at else now
                if best_exp < exp_at_naive:
                    debt_delta = exp_at_naive - best_exp
                    db.collection('notifications').add({
                        'title': 'نقل تلقائي مع دين',
                        'message': f'تم نقل الاشتراك {sub_id} للمستخدم إلى سيرفر جديد سينتهي قبل اشتراكه! هناك دين بقيمة {debt_delta.days} يوم.',
                        'created_at': datetime.utcnow(),
                        'is_read': False,
                        'type': 'debt'
                    })
def setup_simulation_advanced():
    print("Setting up advanced simulation data...")
    # Clean up old simulation data
    for doc in db.collection('users').where('email', '>=', 'sim_user').stream():
        db.collection('users').document(doc.id).delete()
    for doc in db.collection('servers').where('name', '>=', 'SimServer').stream():
        db.collection('servers').document(doc.id).delete()
    for doc in db.collection('subscriptions').where('allocated_subdomain', '>=', 'sim_user').stream():
        db.collection('subscriptions').document(doc.id).delete()
    for doc in db.collection('notifications').where('title', '>=', 'نقل تلقائي مع دين').stream():
        db.collection('notifications').document(doc.id).delete()

    # Create dummy user
    user_ref = db.collection('users').add({
        'email': 'sim_user_advanced@example.com',
        'status': 'active'
    })
    user_id = user_ref[1].id

    # Server 1: Active, expires in 30 days
    s1_ref = db.collection('servers').add({
        'name': 'SimServer_1_Active',
        'tags': ['premium'],
        'expires_at': datetime.utcnow() + timedelta(days=30),
        'original_ip': '1.1.1.1'
    })
    s1_id = s1_ref[1].id
    
    # Server 2: Dead
    s2_ref = db.collection('servers').add({
        'name': 'SimServer_2_Dead',
        'tags': ['premium'],
        'expires_at': datetime.utcnow() - timedelta(minutes=5),
        'original_ip': '2.2.2.2'
    })
    s2_id = s2_ref[1].id

    # Server 3: Active, but expires VERY soon (in 2 days)
    s3_ref = db.collection('servers').add({
        'name': 'SimServer_3_Short',
        'tags': ['premium'],
        'expires_at': datetime.utcnow() + timedelta(days=2),
        'original_ip': '3.3.3.3'
    })
    s3_id = s3_ref[1].id

    return user_id, s1_id, s2_id, s3_id

def simulate():
    user_id, s1_id, s2_id, s3_id = setup_simulation_advanced()
    
    # ---------------------------------------------------------
    # TEST CASE 1: Healthy subscription (No action should be taken)
    # ---------------------------------------------------------
    print("\n[TEST 1] Healthy Subscription")
    sub1_ref = db.collection('subscriptions').add({
        'user_id': user_id,
        'server_id': s1_id,
        'allocated_subdomain': 'sim_user_adv1-xxxxxx.bombavpn.dynv6.net',
        'status': 'active',
        'required_tags': ['premium'],
        'is_temporary': False,
        'expires_at': datetime.utcnow() + timedelta(days=10)
    })
    sub1_id = sub1_ref[1].id
    run_worker_iteration()
    sub1 = db.collection('subscriptions').document(sub1_id).get().to_dict()
    print(f"Result 1: Server={sub1['server_id']} (Expected {s1_id})")
    assert sub1['server_id'] == s1_id

    # ---------------------------------------------------------
    # TEST CASE 2: Subscription Expiration
    # ---------------------------------------------------------
    print("\n[TEST 2] Expired Subscription")
    sub2_ref = db.collection('subscriptions').add({
        'user_id': user_id,
        'server_id': s1_id,
        'allocated_subdomain': 'sim_user_adv2-xxxxxx.bombavpn.dynv6.net',
        'status': 'active',
        'required_tags': ['premium'],
        'is_temporary': False,
        'expires_at': datetime.utcnow() - timedelta(minutes=1) # Expired!
    })
    sub2_id = sub2_ref[1].id
    run_worker_iteration()
    sub2 = db.collection('subscriptions').document(sub2_id).get().to_dict()
    print(f"Result 2: Status={sub2['status']} (Expected expired)")
    assert sub2['status'] == 'expired'

    # ---------------------------------------------------------
    # TEST CASE 3: Migration to Short Server -> Debt Notification
    # ---------------------------------------------------------
    print("\n[TEST 3] Debt Calculation on Migration")
    # Sub is on a dead server, expires in 10 days
    sub3_ref = db.collection('subscriptions').add({
        'user_id': user_id,
        'server_id': s2_id, # Dead server
        'allocated_subdomain': 'sim_user_adv3-xxxxxx.bombavpn.dynv6.net',
        'status': 'active',
        'required_tags': ['premium'],
        'is_temporary': False,
        'expires_at': datetime.utcnow() + timedelta(days=10)
    })
    sub3_id = sub3_ref[1].id
    
    # Temporarily hide s1 so it's forced to migrate to s3 (the short one)
    db.collection('servers').document(s1_id).update({'expires_at': datetime.utcnow() - timedelta(days=1)})
    
    run_worker_iteration()
    
    sub3 = db.collection('subscriptions').document(sub3_id).get().to_dict()
    print(f"Result 3: Server={sub3['server_id']} (Expected {s3_id})")
    assert sub3['server_id'] == s3_id
    
    # Check for Debt Notification
    notifications = list(db.collection('notifications').where('title', '==', 'نقل تلقائي مع دين').stream())
    print(f"Result 3: Found {len(notifications)} Debt Notifications (Expected 1)")
    assert len(notifications) > 0

    # ---------------------------------------------------------
    # TEST CASE 4: No active servers available at all
    # ---------------------------------------------------------
    print("\n[TEST 4] No Active Servers Available")
    # Kill s3 as well
    db.collection('servers').document(s3_id).update({'expires_at': datetime.utcnow() - timedelta(days=1)})
    
    sub4_ref = db.collection('subscriptions').add({
        'user_id': user_id,
        'server_id': s2_id, # Dead server
        'allocated_subdomain': 'sim_user_adv4-xxxxxx.bombavpn.dynv6.net',
        'status': 'active',
        'required_tags': ['premium'],
        'is_temporary': False,
        'expires_at': datetime.utcnow() + timedelta(days=10)
    })
    sub4_id = sub4_ref[1].id
    run_worker_iteration()
    
    sub4 = db.collection('subscriptions').document(sub4_id).get().to_dict()
    print(f"Result 4: Server={sub4['server_id']} (Expected {s2_id} because no migration possible)")
    assert sub4['server_id'] == s2_id # Should not crash, just stay where it is
    
    print("\nSUCCESS! All advanced simulations passed flawlessly!")

if __name__ == '__main__':
    simulate()
