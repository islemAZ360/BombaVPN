import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone
import os

# Initialize Firebase
cred_path = os.path.join(os.path.dirname(__file__), 'bomba-cff9a-firebase-adminsdk-j6x99-07f7cde727.json')
cred = credentials.Certificate(cred_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

def migrate_db():
    users_ref = db.collection('users')
    users = users_ref.stream()
    subs_count = 0
    reqs_count = 0
    
    for user_doc in users:
        data = user_doc.to_dict()
        user_id = user_doc.id
        
        # If user has a server allocated, migrate it to subscriptions
        if data.get('allocated_server_id'):
            existing_subs = db.collection('subscriptions').where('user_id', '==', user_id).where('server_id', '==', data.get('allocated_server_id')).stream()
            has_existing = any(True for _ in existing_subs)
            
            if not has_existing:
                sub_data = {
                    'user_id': user_id,
                    'server_id': data.get('allocated_server_id'),
                    'allocated_subdomain': data.get('allocated_subdomain'),
                    'expires_at': data.get('subscription_expires_at'),
                    'status': data.get('status', 'expired'),
                    'created_at': datetime.now(timezone.utc)
                }
                
                db.collection('subscriptions').add(sub_data)
                subs_count += 1
                
        # If user has a pending request, migrate it to purchase_requests
        if data.get('status') in ['pending', 'review'] and data.get('requested_server_id'):
            existing_reqs = db.collection('purchase_requests').where('user_id', '==', user_id).where('server_id', '==', data.get('requested_server_id')).stream()
            if not any(True for _ in existing_reqs):
                req_data = {
                    'user_id': user_id,
                    'server_id': data.get('requested_server_id'),
                    'receipt_url': data.get('receipt_url'),
                    'status': data.get('status'),
                    'created_at': datetime.now(timezone.utc)
                }
                db.collection('purchase_requests').add(req_data)
                reqs_count += 1
                
    print(f"Migrated {subs_count} active subscriptions and {reqs_count} pending requests.")

if __name__ == '__main__':
    migrate_db()
