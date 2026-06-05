def manage_subscription(sub_id):
    if not request.is_admin: return "Unauthorized", 403
    action = request.form.get('action')
    
    sub_doc = db.collection('subscriptions').document(sub_id).get()
    if not sub_doc.exists: return redirect(url_for('admin_dashboard'))
    data = sub_doc.to_dict()
    user_id = data.get('user_id')
    user_doc = db.collection('users').document(user_id).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    
    if action == 'cancel':
        update_data = {'status': 'expired'}
        if data.get('allocated_subdomain'):
            delete_dns_record(data['allocated_subdomain'], DYNV6_TOKEN)
            update_data['allocated_subdomain'] = None
            update_data['server_id'] = None
        db.collection('subscriptions').document(sub_id).update(update_data)
        flash('تم إلغاء الاشتراك بنجاح / Subscription cancelled', 'success')
        
    elif action == 'modify':
        modify_type = request.form.get('modify_type', 'add')
        days = int(request.form.get('days') or 0)
        hours = int(request.form.get('hours') or 0)
        minutes = int(request.form.get('minutes') or 0)
        seconds = int(request.form.get('seconds') or 0)
        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        
        current_expires = data.get('expires_at')
        if current_expires:
            if current_expires.tzinfo is None:
                current_expires = current_expires.replace(tzinfo=timezone.utc)
        else:
            current_expires = datetime.now(timezone.utc)
            
        if modify_type == 'add':
            new_expires = current_expires + delta
        elif modify_type == 'subtract':
            new_expires = current_expires - delta
        else: # set
            new_expires = datetime.now(timezone.utc) + delta
            
        # Make sure new_expires is timezone aware
        if new_expires.tzinfo is None:
            new_expires = new_expires.replace(tzinfo=timezone.utc)
            
        db.collection('subscriptions').document(sub_id).update({
            'expires_at': new_expires,
            'status': 'active' if new_expires > datetime.now(timezone.utc) else 'expired'
        })
        flash('تم تعديل مدة الاشتراك بنجاح / Subscription duration modified', 'success')
        
    elif action == 'assign':
        server_id = request.form.get('server_id')
        if server_id:
            s_doc = db.collection('servers').document(server_id).get()
            if s_doc.exists:
                s_data = s_doc.to_dict()
                email_val = user_data.get('email', f'user-{user_id}')
                subdomain = f"{email_val.replace('@', '-').replace('.', '-')}-{sub_id[:4]}.{BASE_ZONE}"
                
                old_subdomain = data.get('allocated_subdomain')
                if old_subdomain != subdomain or data.get('server_id') != server_id:
                    if old_subdomain: delete_dns_record(old_subdomain, DYNV6_TOKEN)
                    create_dns_record(subdomain, s_data['original_ip'], DYNV6_TOKEN)
                
                db.collection('subscriptions').document(sub_id).update({
                    'server_id': server_id,
                    'allocated_subdomain': subdomain,
                    'status': 'active'
                })
                flash('تم تعيين السيرفر للاشتراك بنجاح / Server assigned to subscription', 'success')
                
    return redirect(url_for('admin_dashboard'))

@