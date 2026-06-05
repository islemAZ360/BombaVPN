import re

with open('app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove dns_manager import
code = re.sub(r'from dns_manager import create_dns_record, delete_dns_record\n?', '', code)

# 2. Remove DYNV6 config
code = re.sub(r"DYNV6_TOKEN = os\.environ\.get\('DYNV6_TOKEN', 'YOUR_DYNV6_TOKEN_HERE'\)\n?", '', code)
code = re.sub(r"BASE_ZONE = os\.environ\.get\('BASE_ZONE', 'galaxyvpn\.dynv6\.net'\)\n?", '', code)

# 3. Update pay() to save renew_sub_id
pay_str_old = """            # Save the new purchase request in the dedicated collection
            db.collection('purchase_requests').add({
                'user_id': user_id,
                'email': request.user['email'],
                'server_id': server_id,"""
pay_str_new = """            # Save the new purchase request in the dedicated collection
            renew_sub_id = request.form.get('renew_sub_id')
            db.collection('purchase_requests').add({
                'user_id': user_id,
                'email': request.user['email'],
                'server_id': server_id,
                'renew_sub_id': renew_sub_id,"""
code = code.replace(pay_str_old, pay_str_new)

# 4. Update delete_server
del_server_old = """@app.route('/admin/delete_server/<server_id>', methods=['POST'])
@login_required
def delete_server(server_id):
    if not request.is_admin: return "Unauthorized", 403
    
    # Flag users for auto-recovery
    users_on_server = db.collection('users').where('allocated_server_id', '==', server_id).stream()
    for udoc in users_on_server:
        db.collection('users').document(udoc.id).update({
            'is_in_debt': True
        })
        
    db.collection('servers').document(server_id).delete()"""
del_server_new = """@app.route('/admin/delete_server/<server_id>', methods=['POST'])
@login_required
def delete_server(server_id):
    if not request.is_admin: return "Unauthorized", 403
        
    db.collection('servers').document(server_id).delete()"""
code = code.replace(del_server_old, del_server_new)

# 5. Clean approve_request
approve_old = """        email_val = user_data.get('email', '')
        if email_val:
            safe_prefix = email_val.replace('@', '-').replace('.', '-')
            # Unique subdomain per subscription: prefix-serverid.dynv6.net
            subdomain = f"{safe_prefix}-{server_id[:6]}.{BASE_ZONE}"
            create_dns_record(subdomain, s_data['original_ip'], DYNV6_TOKEN)
            
    duration_delta = timedelta(days=days, hours=hours, minutes=minutes)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + duration_delta
    
    # Check if server expires before the subscription
    is_temporary = False
    if s_data:
        s_expires = s_data.get('expires_at')
        if s_expires:
            s_expires = s_expires.replace(tzinfo=None)
            if s_expires < expires_at:
                debt_delta = expires_at - s_expires
                db.collection('notifications').add({
                    'title': 'تنبيه ديون (السيرفر سينتهي قريباً)',
                    'message': f'المستخدم {user_data.get("email")} لديه اشتراك يتجاوز عمر السيرفر المختار. نظام النقل التلقائي سيتدخل لاحقاً لنقله لسيرفر جديد ليكمل الـ {debt_delta.days} يوم المتبقية.',
                    'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                    'is_read': False,
                    'type': 'debt'
                })
    
    # Save to the subscriptions collection
    db.collection('subscriptions').add({
        'user_id': user_id,
        'server_id': server_id,
        'allocated_subdomain': subdomain,
        'status': 'active',
        'required_tags': s_data.get('tags', []) if s_data else [],
        'is_temporary': False,
        'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
        'expires_at': expires_at
    })"""
    
approve_new = """    duration_delta = timedelta(days=days, hours=hours, minutes=minutes)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + duration_delta
    
    # Check if server expires before the subscription
    if s_data:
        s_expires = s_data.get('expires_at')
        if s_expires:
            s_expires = s_expires.replace(tzinfo=None)
            if s_expires < expires_at:
                debt_delta = expires_at - s_expires
                db.collection('notifications').add({
                    'title': 'تنبيه ديون (السيرفر سينتهي قريباً)',
                    'message': f'المستخدم {user_data.get("email")} لديه اشتراك يتجاوز عمر السيرفر المختار. نظام النقل التلقائي سيتدخل لاحقاً لنقله لسيرفر جديد ليكمل الـ {debt_delta.days} يوم المتبقية.',
                    'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                    'is_read': False,
                    'type': 'debt'
                })
    
    renew_sub_id = req_data.get('renew_sub_id')
    if renew_sub_id:
        sub_ref = db.collection('subscriptions').document(renew_sub_id)
        if sub_ref.get().exists:
            sub_ref.update({
                'server_id': server_id,
                'status': 'active',
                'required_tags': s_data.get('tags', []) if s_data else [],
                'is_temporary': False,
                'expires_at': expires_at
            })
        else:
            db.collection('subscriptions').add({
                'user_id': user_id,
                'server_id': server_id,
                'status': 'active',
                'required_tags': s_data.get('tags', []) if s_data else [],
                'is_temporary': False,
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                'expires_at': expires_at
            })
    else:
        db.collection('subscriptions').add({
            'user_id': user_id,
            'server_id': server_id,
            'status': 'active',
            'required_tags': s_data.get('tags', []) if s_data else [],
            'is_temporary': False,
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
            'expires_at': expires_at
        })"""
code = code.replace(approve_old, approve_new)

# 6. Clean all remaining dynv6 calls inside background tasks
code = re.sub(r'[ \t]*delete_dns_record\([^)]+\)\n?', '', code)
code = re.sub(r'[ \t]*create_dns_record\([^)]+\)\n?', '', code)

# Clean out old `subdomain` references inside background task since they're no longer initialized
code = code.replace("old_subdomain = sub.get('allocated_subdomain')\n                                if old_subdomain and old_subdomain != subdomain:", "")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("App patched successfully")
