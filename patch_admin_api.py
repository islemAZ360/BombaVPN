import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_api = """
@app.route('/api/admin/dashboard_sync')
@login_required
def api_dashboard_sync():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    servers_list = []
    with servers_cache_lock:
        for s_id, s_dict in servers_cache.items():
            s = s_dict.copy()
            s['id'] = s_id
            if s.get('expires_at') and isinstance(s['expires_at'], datetime):
                s['expires_at'] = s['expires_at'].replace(tzinfo=None)
            servers_list.append(s)
            
    server_stats = {
        'total': len(servers_list),
        'gemini': sum(1 for s in servers_list if 'Gemini' in s.get('tags', [])),
        'yt': sum(1 for s in servers_list if 'YT' in s.get('tags', [])),
        'lte': sum(1 for s in servers_list if 'LTE' in s.get('tags', [])),
        'ru': sum(1 for s in servers_list if 'RU' in s.get('tags', [])),
        'torrent': sum(1 for s in servers_list if 'Torrent' in s.get('tags', []))
    }
    
    users_dict = {}
    all_users = []
    active_users = []
    
    with users_cache_lock:
        for u_id, u_dict in users_cache.items():
            u = u_dict.copy()
            u['id'] = u_id
            if u.get('created_at') and isinstance(u['created_at'], datetime):
                u['created_at'] = u['created_at'].replace(tzinfo=None)
            u['subscriptions'] = []
            users_dict[u_id] = u
            all_users.append(u)
            
    server_map = {s['id']: s.get('name') for s in servers_list}
    
    with subscriptions_cache_lock:
        for sub_id, sub_dict in subscriptions_cache.items():
            sub = sub_dict.copy()
            sub['id'] = sub_id
            if sub.get('expires_at') and isinstance(sub['expires_at'], datetime):
                sub['expires_at'] = sub['expires_at'].replace(tzinfo=None)
            uid = sub.get('user_id')
            if uid in users_dict:
                if sub.get('server_id'):
                    sub['allocated_server_name'] = server_map.get(sub['server_id'], 'Unknown')
                users_dict[uid]['subscriptions'].append(sub)
                
    for u in all_users:
        is_active = any(s.get('status') == 'active' for s in u['subscriptions'])
        is_expired = any(s.get('status') == 'expired' for s in u['subscriptions'])
        if is_active:
            u['status'] = 'active'
            active_users.append(u)
        elif is_expired:
            u['status'] = 'expired'
        elif u.get('status') != 'pending':
            u['status'] = 'no_sub'
            
    tickets = []
    with messages_cache_lock:
        for m_id, m_dict in messages_cache.items():
            msg = m_dict.copy()
            msg['id'] = m_id
            if msg.get('created_at') and isinstance(msg['created_at'], datetime):
                msg['created_at'] = msg['created_at'].replace(tzinfo=None)
            tickets.append(msg)
            
    tickets.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
    
    # Serialize datetimes to ISO format for JSON
    def serialize_dates(obj):
        if isinstance(obj, list):
            for item in obj:
                serialize_dates(item)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, datetime):
                    obj[k] = v.isoformat()
                elif isinstance(v, (dict, list)):
                    serialize_dates(v)
                    
    payload = {
        'server_stats': server_stats,
        'all_users': all_users,
        'active_users': active_users,
        'servers': servers_list,
        'tickets': tickets
    }
    serialize_dates(payload)
    
    return jsonify(payload)

@app.route('/api/admin/debts_sync')
@login_required
def api_debts_sync():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    in_debt_users = []
    
    servers_map = {}
    with servers_cache_lock:
        for s_id, s_dict in servers_cache.items():
            servers_map[s_id] = s_dict.copy()
            
    with subscriptions_cache_lock:
        for sub_id, sub_dict in subscriptions_cache.items():
            if sub_dict.get('status') == 'active':
                server_id = sub_dict.get('server_id')
                sub_exp = sub_dict.get('expires_at')
                if not server_id or not sub_exp:
                    continue
                if isinstance(sub_exp, datetime):
                    sub_exp = sub_exp.replace(tzinfo=None)
                    
                s_data = servers_map.get(server_id)
                if not s_data: continue
                s_exp = s_data.get('expires_at')
                if not s_exp: continue
                if isinstance(s_exp, datetime):
                    s_exp = s_exp.replace(tzinfo=None)
                    
                if s_exp < sub_exp:
                    delta = sub_exp - s_exp
                    user_id = sub_dict.get('user_id')
                    u_email = "Unknown"
                    with users_cache_lock:
                        if user_id in users_cache:
                            u_email = users_cache[user_id].get('email', 'Unknown')
                            
                    in_debt_users.append({
                        'id': sub_id,
                        'email': u_email,
                        'server_name': s_data.get('name', 'Unknown'),
                        'server_expires_at': s_exp.isoformat() if isinstance(s_exp, datetime) else str(s_exp),
                        'subscription_expires_at': sub_exp.isoformat() if isinstance(sub_exp, datetime) else str(sub_exp),
                        'debt_days': delta.days,
                        'debt_hours': delta.seconds // 3600
                    })
                    
    return jsonify({'debts': in_debt_users})
"""

target_str = "@app.route('/api/admin/pending_requests')"
if target_str in content:
    content = content.replace(target_str, new_api + "\n\n" + target_str)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("API endpoints added successfully.")
else:
    print("Could not find target string.")
