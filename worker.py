import time
import json
import os
from datetime import datetime, timezone, timedelta
from supabase_client import supabase_admin

def background_expiry_checker():
    print("Starting Standalone Auto-Migration background worker...")
    print("This worker checks for expired subscriptions and migrates them if needed.")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # Fetch active servers directly from Supabase
            all_active_servers = []
            servers_resp = supabase_admin.table('servers').select('*').execute()
            servers = servers_resp.data if servers_resp and servers_resp.data else []
            for s in servers:
                s_expires_str = s.get('expires_at')
                if s_expires_str:
                    try:
                        s_expires = datetime.fromisoformat(s_expires_str.replace('Z', '+00:00'))
                        if s_expires > now:
                            s['expires_at_dt'] = s_expires
                            all_active_servers.append(s)
                    except:
                        pass

            # Check all active subscriptions
            subs_resp = supabase_admin.table('subscriptions').select('*').eq('status', 'active').execute()
            active_subs = subs_resp.data if subs_resp and subs_resp.data else []
            
            for sub in active_subs:
                try:
                    sub_id = sub.get('id')
                    
                    expires_at_str = sub.get('expires_at')
                    expires_at = None
                    if expires_at_str:
                        try:
                            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                        except:
                            pass
                            
                    if expires_at:
                        if datetime.now(timezone.utc) > expires_at:
                            print(f"Background check: Subscription {sub_id} expired.")
                            supabase_admin.table('subscriptions').update({
                                'status': 'expired',
                                'allocated_subdomain': None
                            }).eq('id', sub_id).execute()
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
                            best_server = max(candidate_servers, key=lambda s: s['expires_at_dt'])
                            new_temp = False
                        elif server_dead:
                            if not all_active_servers:
                                # No active servers available to migrate this user!
                                user_resp = supabase_admin.table('users').select('*').eq('id', sub.get('user_id')).execute()
                                user_email = 'Unknown'
                                if user_resp.data:
                                    user_email = user_resp.data[0].get('email', 'Unknown')
                                    
                                supabase_admin.table('subscriptions').update({
                                    'server_id': None,
                                    'allocated_subdomain': None
                                }).eq('id', sub_id).execute()
                                
                                supabase_admin.table('notifications').insert({
                                    'title': 'اشتراك بدون سيرفر / Sub without server',
                                    'message': f'انتهى السيرفر الخاص بالمشترك / Server ended for user {user_email} ولا توجد سيرفرات نشطة بديلة! / and no active servers available! تم فصل السيرفر عنه مؤقتاً لحين إضافة أو تجديد سيرفر. / Server temporarily disconnected.',
                                    'created_at': datetime.now(timezone.utc).isoformat(),
                                    'is_read': False,
                                    'type': 'system'
                                }).execute()
                                continue
                            best_server = max(all_active_servers, key=lambda s: s['expires_at_dt'])
                            new_temp = True
                        else:
                            continue
                            
                        if best_server['id'] != allocated_server_id:
                            user_resp = supabase_admin.table('users').select('*').eq('id', sub.get('user_id')).execute()
                            if user_resp.data:
                                user_data = user_resp.data[0]
                                
                                supabase_admin.table('subscriptions').update({
                                    'server_id': best_server['id'],
                                    'allocated_subdomain': None,
                                    'is_temporary': new_temp
                                }).eq('id', sub_id).execute()
                                
                                best_exp = best_server['expires_at_dt']
                                exp_at_naive = expires_at if expires_at else now
                                if best_exp < exp_at_naive:
                                    debt_delta = exp_at_naive - best_exp
                                    supabase_admin.table('notifications').insert({
                                        'title': 'نقل تلقائي مع دين / Auto-migration with debt',
                                        'message': f'تم نقل الاشتراك / Sub {sub_id} migrated للمستخدم / for user {user_data.get("email")} إلى سيرفر جديد سينتهي قبل اشتراكه! / to a new server ending before their sub! هناك دين بقيمة / Debt is {debt_delta.days} يوم / days.',
                                        'created_at': datetime.now(timezone.utc).isoformat(),
                                        'is_read': False,
                                        'type': 'debt'
                                    }).execute()
                                elif original_server_active:
                                    supabase_admin.table('notifications').insert({
                                        'title': 'العودة للسيرفر الأصلي / Returned to original server',
                                        'message': f'تم إرجاع المشترك / User {user_data.get("email")} إلى سيرفره الأصلي / returned to original server {best_server.get("name")} بعد أن عاد للعمل. / after it became active again.',
                                        'created_at': datetime.now(timezone.utc).isoformat(),
                                        'is_read': False,
                                        'type': 'system'
                                    }).execute()
                except Exception as e:
                    print(f"Error processing sub {sub_id} in background task: {e}")
                    continue
        except Exception as e:
            print(f"Background expiry checker error: {e}")
            
        # Run every 30 seconds
        time.sleep(30)

if __name__ == '__main__':
    try:
        background_expiry_checker()
    except KeyboardInterrupt:
        print("Worker stopped.")
