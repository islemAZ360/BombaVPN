import time
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

# --- Firebase Initialization ---
cred_path = os.path.join(os.path.dirname(__file__), 'firebase-adminsdk.json')
cred = credentials.Certificate(cred_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

def background_expiry_checker():
    print("Starting Standalone Auto-Migration background worker...")
    print("This worker checks for expired subscriptions and migrates them if needed.")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # Fetch active servers directly from Firebase
            all_active_servers = []
            for doc in db.collection('servers').stream():
                s = doc.to_dict()
                s['id'] = doc.id
                s_expires = s.get('expires_at')
                if s_expires and s_expires > now:
                    all_active_servers.append(s)

            # Check all active subscriptions
            for doc in db.collection('subscriptions').where('status', '==', 'active').stream():
                try:
                    sub_id = doc.id
                    sub = doc.to_dict()
                    
                    expires_at = sub.get('expires_at')
                    if expires_at:
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) > expires_at:
                            print(f"Background check: Subscription {sub_id} expired.")
                            update_data = {'status': 'expired'}
                            update_data['allocated_subdomain'] = None
                            db.collection('subscriptions').document(sub_id).update(update_data)
                            continue
                            
                    server_dead = True
                    allocated_server_id = sub.get('server_id')
                    if allocated_server_id:
                        for active_s in all_active_servers:
                            if active_s['id'] == allocated_server_id:
                                server_dead = False
                                break
                                
                    is_temp = sub.get('is_temporary', False)
                    original_server_id = sub.get('original_server_id')
                    
                    # Check if the original server has come back to life
                    original_server_active = False
                    if original_server_id and original_server_id != allocated_server_id:
                        for active_s in all_active_servers:
                            if active_s['id'] == original_server_id:
                                original_server_active = True
                                break
                    
                    if server_dead or is_temp or original_server_active:
                        required_tags = set(sub.get('required_tags') or [])
                        candidate_servers = []
                        for s in all_active_servers:
                            s_tags = set(s.get('tags') or [])
                            if required_tags.issubset(s_tags):
                                candidate_servers.append(s)
                                
                        if original_server_active:
                            # Force return to the original server since it's alive again
                            best_server = next(s for s in all_active_servers if s['id'] == original_server_id)
                            new_temp = False
                        elif candidate_servers:
                            best_server = max(candidate_servers, key=lambda s: s['expires_at'])
                            new_temp = False
                        elif server_dead:
                            if not all_active_servers:
                                # No active servers available to migrate this user!
                                user_doc = db.collection('users').document(sub.get('user_id')).get()
                                user_email = user_doc.to_dict().get('email', 'Unknown') if user_doc.exists else 'Unknown'
                                db.collection('subscriptions').document(sub_id).update({
                                    'server_id': None,
                                    'allocated_subdomain': None
                                })
                                db.collection('notifications').add({
                                    'title': 'اشتراك بدون سيرفر / Sub without server',
                                    'message': f'انتهى السيرفر الخاص بالمشترك / Server ended for user {user_email} ولا توجد سيرفرات نشطة بديلة! / and no active servers available! تم فصل السيرفر عنه مؤقتاً لحين إضافة أو تجديد سيرفر. / Server temporarily disconnected.',
                                    'created_at': datetime.now(timezone.utc),
                                    'is_read': False,
                                    'type': 'system'
                                })
                                continue
                            best_server = max(all_active_servers, key=lambda s: s['expires_at'])
                            new_temp = True
                        else:
                            continue
                            
                        if best_server['id'] != allocated_server_id:
                            user_doc = db.collection('users').document(sub.get('user_id')).get()
                            if user_doc.exists:
                                user_data = user_doc.to_dict()
                                
                                db.collection('subscriptions').document(sub_id).update({
                                    'server_id': best_server['id'],
                                    'allocated_subdomain': None,
                                    'is_temporary': new_temp
                                })
                                
                                best_exp = best_server['expires_at']
                                exp_at_naive = expires_at if expires_at else now
                                if best_exp < exp_at_naive:
                                    debt_delta = exp_at_naive - best_exp
                                    db.collection('notifications').add({
                                        'title': 'نقل تلقائي مع دين / Auto-migration with debt',
                                        'message': f'تم نقل الاشتراك / Sub {sub_id} migrated للمستخدم / for user {user_data.get("email")} إلى سيرفر جديد سينتهي قبل اشتراكه! / to a new server ending before their sub! هناك دين بقيمة / Debt is {debt_delta.days} يوم / days.',
                                        'created_at': datetime.now(timezone.utc),
                                        'is_read': False,
                                        'type': 'debt'
                                    })
                                elif original_server_active:
                                    db.collection('notifications').add({
                                        'title': 'العودة للسيرفر الأصلي / Returned to original server',
                                        'message': f'تم إرجاع المشترك / User {user_data.get("email")} إلى سيرفره الأصلي / returned to original server {best_server.get("name")} بعد أن عاد للعمل. / after it became active again.',
                                        'created_at': datetime.now(timezone.utc),
                                        'is_read': False,
                                        'type': 'system'
                                    })
                except Exception as e:
                    print(f"Error processing sub {sub_id} in background task: {e}")
                    continue
        except Exception as e:
            print(f"Background expiry checker error: {e}")
            
        # Run every 300 seconds
        time.sleep(300)

if __name__ == '__main__':
    try:
        background_expiry_checker()
    except KeyboardInterrupt:
        print("Worker stopped.")
