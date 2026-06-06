
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, current_app
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
import json
import uuid
import requests
from firebase_admin import firestore
from extensions import db, limiter, login_required, FIREBASE_READY, sub_serializer, firebase_auth
from db_helpers import get_all_users, get_all_servers, get_all_messages, get_all_subscriptions, get_all_pricing_rules, get_all_source_links
from utils import extract_ip_from_json, modify_json_address, extract_name_from_json, generate_vless_uri, generate_full_config
from vless_parser import extract_vless_from_text
import urllib.parse
import socket
import ipaddress
import threading
from helpers import *
from helpers import _import_vless_servers, _approve_request_logic, _reject_request_logic

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@login_required
def admin_dashboard():
    if not request.is_admin:
        return "Unauthorized", 403
        
    servers = []
    for doc in db.collection('servers').stream():
        data = doc.to_dict()
        data['id'] = doc.id
        if 'expires_at' in data and data['expires_at']:
            data['expires_at'] = data['expires_at']
        servers.append(data)
    
    # Sort servers: group by country, then by number
    import re as _re
    def server_sort_key(s):
        name = s.get('name', '')
        base = name.split('|')[0].strip()
        match = _re.match(r'^(.+?)\s*#(\d+)$', base)
        if match:
            country = match.group(1).strip()
            num = int(match.group(2))
        else:
            country = base
            num = 0
        return (country.lower(), num)
    servers.sort(key=server_sort_key)
        

    pending_users = []
    active_users = []
    all_users = []
    users_dict = {}
    
    for doc in db.collection('users').stream():
        data = doc.to_dict()
        data['id'] = doc.id
        if 'created_at' in data and data['created_at']:
            data['created_at'] = data['created_at']
            
        data['subscriptions'] = []
        users_dict[data['id']] = data
        all_users.append(data)
        
    server_map = {s['id']: s.get('name') for s in servers}
    
    # Fetch all subscriptions
    for doc in db.collection('subscriptions').stream():
        sub = doc.to_dict()
        sub['id'] = doc.id
        if 'expires_at' in sub and sub['expires_at']:
            sub['expires_at'] = sub['expires_at']
            
        uid = sub.get('user_id')
        if uid in users_dict:
            if sub.get('server_id'):
                sub['allocated_server_name'] = server_map.get(sub['server_id'], 'Unknown')
            users_dict[uid]['subscriptions'].append(sub)
            
    # Update active_users based on subscriptions
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
            
    # Fetch pending purchase requests
    for doc in db.collection('purchase_requests').where('status', '==', 'pending').stream():
        req = doc.to_dict()
        req['id'] = doc.id
        
        # Attach user data
        user_doc = db.collection('users').document(req['user_id']).get()
        if user_doc.exists:
            req['user'] = user_doc.to_dict()
            if 'email' not in req:
                req['email'] = req['user'].get('email')
        
        req['receipt_image'] = req.get('receipt_url')
        req['requested_server_id'] = req.get('server_id')
        req['is_renewal'] = False # Not strictly needed if they are all just purchase requests
        
        pending_users.append(req)
        
    for u in pending_users:
        s_id = u.get('requested_server_id')
        if s_id:
            s_doc = db.collection('servers').document(s_id).get()
            if s_doc.exists:
                u['server'] = s_doc.to_dict()
            
    now = datetime.now(timezone.utc)
    
    # Fetch support tickets
    tickets = []
    try:
        for doc in db.collection('messages').order_by('created_at', direction=firestore.Query.DESCENDING).stream():
            msg = doc.to_dict()
            msg['id'] = doc.id
            if 'created_at' in msg and msg['created_at']:
                msg['created_at'] = msg['created_at']
            tickets.append(msg)
    except Exception as e:
        print("Error fetching tickets:", e)
            
    server_stats = {
        'total': len(servers),
        'gemini': sum(1 for s in servers if 'gemini' in [t.lower() for t in s.get('tags', [])]),
        'yt': sum(1 for s in servers if 'yt' in [t.lower() for t in s.get('tags', [])]),
        'lte': sum(1 for s in servers if 'lte' in [t.lower() for t in s.get('tags', [])]),
        'ru': sum(1 for s in servers if 'ru' in [t.lower() for t in s.get('tags', [])]),
        'torrent': sum(1 for s in servers if 'torrent' in [t.lower() for t in s.get('tags', [])])
    }
    
    return render_template('admin_dashboard.html', servers=servers, pending_users=pending_users, active_users=active_users, all_users=all_users, tickets=tickets, now=now, server_stats=server_stats)

@admin_bp.route('/admin/notifications')
@login_required
def admin_notifications():
    if not request.is_admin:
        return "Unauthorized", 403
        
    notifications = []
    try:
        for doc in db.collection('notifications').order_by('created_at', direction=firestore.Query.DESCENDING).limit(50).stream():
            n = doc.to_dict()
            n['id'] = doc.id
            if 'created_at' in n and n['created_at']:
                n['created_at'] = n['created_at']
            notifications.append(n)
    except Exception as e:
        print("Error fetching notifications:", e)
        
    return render_template('notifications.html', notifications=notifications)

@admin_bp.route('/admin/notifications/read/<notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    if not request.is_admin:
        return "Unauthorized", 403
    db.collection('notifications').document(notif_id).update({'is_read': True})
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_parent'}), 200
    return redirect(url_for('admin.admin_notifications'))

@admin_bp.route('/admin/notifications/read_all', methods=['POST'])
@login_required
def mark_all_read():
    if not request.is_admin:
        return "Unauthorized", 403
    for doc in db.collection('notifications').where('is_read', '==', False).stream():
        db.collection('notifications').document(doc.id).update({'is_read': True})
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_all_notifications', 'message': 'All notifications marked as read'}), 200
    return redirect(url_for('admin.admin_notifications'))

@admin_bp.route('/admin/notifications/delete/<notif_id>', methods=['POST'])
@login_required
def delete_notif(notif_id):
    if not request.is_admin:
        return "Unauthorized", 403
    db.collection('notifications').document(notif_id).delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_parent'}), 200
    return redirect(url_for('admin.admin_notifications'))

@admin_bp.route('/admin/notifications/delete_all', methods=['POST'])
@login_required
def delete_all_notifs():
    if not request.is_admin:
        return "Unauthorized", 403
    for doc in db.collection('notifications').stream():
        db.collection('notifications').document(doc.id).delete()
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_all_notifications', 'message': 'All notifications deleted'}), 200
    return redirect(url_for('admin.admin_notifications'))

@admin_bp.route('/admin/debts')
@login_required
def admin_debts():
    if not request.is_admin:
        return "Unauthorized", 403
        
    in_debt_users = []
    try:
        now = datetime.now(timezone.utc)
        
        # Pre-fetch servers to avoid many DB calls
        servers_map = {}
        if True:
            for s_id, s_dict in get_all_servers().items():
                servers_map[s_id] = s_dict.copy()
                
        # Iterate over all active subscriptions to find debts
        for doc in db.collection('subscriptions').where('status', '==', 'active').stream():
            sub = doc.to_dict()
            sub_id = doc.id
            user_id = sub.get('user_id')
            server_id = sub.get('server_id')
            sub_exp = sub.get('expires_at')
            
            if not server_id or not sub_exp:
                continue
                
            if sub_exp.tzinfo is None:
                sub_exp = sub_exp.replace(tzinfo=timezone.utc)
            sub_exp = sub_exp
            
            s_data = servers_map.get(server_id)
            if not s_data:
                s_doc = db.collection('servers').document(server_id).get()
                if s_doc.exists:
                    s_data = s_doc.to_dict()
                    servers_map[server_id] = s_data
                else:
                    continue
                    
            s_exp = s_data.get('expires_at')
            if not s_exp:
                continue
                
            if s_exp.tzinfo is None:
                s_exp = s_exp.replace(tzinfo=timezone.utc)
            s_exp = s_exp
            
            if s_exp < sub_exp:
                delta = sub_exp - s_exp
                
                u_email = "Unknown"
                if True:
                    if user_id in get_all_users():
                        u_email = get_all_users()[user_id].get('email', 'Unknown')
                if u_email == "Unknown":
                    u_doc = db.collection('users').document(user_id).get()
                    if u_doc.exists:
                        u_email = u_doc.to_dict().get('email', 'Unknown')
                        
                in_debt_users.append({
                    'id': sub_id,
                    'email': u_email,
                    'server_name': s_data.get('name', 'Unknown'),
                    'server_expires_at': s_exp,
                    'subscription_expires_at': sub_exp,
                    'debt_days': delta.days,
                    'debt_hours': delta.seconds // 3600
                })
    except Exception as e:
        print("Error fetching debts:", e)
        
    return render_template('debts.html', users=in_debt_users, now=datetime.now(timezone.utc))

@admin_bp.route('/admin/add_servers', methods=['POST'])
@login_required
def add_servers():
    if not request.is_admin:
        return "Unauthorized", 403
        
    files = request.files.getlist('json_files')
    plan_months = int(request.form.get('plan_months') or 0)
    plan_days = int(request.form.get('plan_days') or 0)
    plan_hours = int(request.form.get('plan_hours') or 0)
    plan_minutes = int(request.form.get('plan_minutes') or 0)
    plan_seconds = int(request.form.get('plan_seconds') or 0)
    
    real_months = int(request.form.get('real_months') or 0)
    real_days = int(request.form.get('real_days') or 0)
    real_hours = int(request.form.get('real_hours') or 0)
    real_minutes = int(request.form.get('real_minutes') or 0)
    real_seconds = int(request.form.get('real_seconds') or 0)
    
    # Normalize mathematically
    total_plan_seconds = (plan_months * 30 * 24 * 3600) + (plan_days * 24 * 3600) + (plan_hours * 3600) + (plan_minutes * 60) + plan_seconds
    total_real_seconds = (real_months * 30 * 24 * 3600) + (real_days * 24 * 3600) + (real_hours * 3600) + (real_minutes * 60) + real_seconds
    
    price = request.form.get('price') or ''
    
    if total_real_seconds == 0:
        expires_at = None
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=total_real_seconds)
    
    added = 0
    existing_servers = [s.to_dict().get('name', '') for s in db.collection('servers').stream()]
    
    # Pre-parse files
    file_data_list = []
    ips_to_query = []
    for file in files:
        if file and file.filename.endswith('.json'):
            content = file.read().decode('utf-8')
            ip = extract_ip_from_json(content)
            file_data_list.append((file.filename, content, ip))
            if ip:
                ips_to_query.append(ip)
                
    country_map = get_country_info_bulk(ips_to_query)
    
    for filename, content, ip in file_data_list:
        if ip:
            orig_name = extract_name_from_json(content) or filename.replace('.json', '')
            orig_name_lower = orig_name.lower()
            
            country_name = "Unknown"
            cc = None
            if ip in country_map:
                country_name, cc = country_map[ip]
                
                if country_name == "Unknown":
                    n_lower = orig_name_lower.replace('-', ' ').replace('_', ' ').replace('|', ' ')
                    words = n_lower.split()
                    if 'russia' in n_lower or 'ru' in words: country_name, cc = "Russia", "RU"
                    elif 'germany' in n_lower or 'de' in words: country_name, cc = "Germany", "DE"
                    elif 'estonia' in n_lower or 'ee' in words: country_name, cc = "Estonia", "EE"
                    elif 'latvia' in n_lower or 'lv' in words: country_name, cc = "Latvia", "LV"
                    elif 'netherlands' in n_lower or 'nl' in words: country_name, cc = "Netherlands", "NL"
                    elif 'france' in n_lower or 'fr' in words: country_name, cc = "France", "FR"
                    elif 'uk' in words or 'united kingdom' in n_lower: country_name, cc = "United Kingdom", "GB"
                    elif 'usa' in words or 'us' in words or 'america' in n_lower: country_name, cc = "United States", "US"
                    
                # Determine the # number by finding the max existing number
                max_num = 0
                for s_name in existing_servers:
                    base_part = s_name.split('|')[0].strip()
                    if base_part == country_name:
                        if max_num < 1: max_num = 1
                    elif base_part.startswith(f"{country_name} #"):
                        try:
                            num = int(base_part.replace(f"{country_name} #", ""))
                            if num > max_num: max_num = num
                        except:
                            pass
                
                count = max_num + 1
                if count == 1:
                    base_name = country_name
                else:
                    base_name = f"{country_name} #{count}"
                
                # Extract keywords
                keywords = []
                if 'gemini' in orig_name_lower: keywords.append("Gemini")
                if 'lte' in orig_name_lower: keywords.append("LTE")
                if 'yt' in orig_name_lower: keywords.append("YT")
                if 'ru' in orig_name_lower: keywords.append("RU")
                
                if keywords:
                    final_name = f"{base_name} | {' | '.join(keywords)}"
                else:
                    final_name = base_name
                    
                existing_servers.append(final_name) # update for the next file in the loop

                db.collection('servers').add({
                    'name': final_name,
                    'original_ip': ip,
                    'country_code': cc.lower() if cc else None,
                    'json_config': content,
                    'price': price,
                    'plan_days': plan_days,
                    'plan_hours': plan_hours,
                    'plan_minutes': plan_minutes,
                    'tags': keywords,
                    'created_at': datetime.now(timezone.utc),
                    'expires_at': expires_at
                })
                added += 1
                
    flash(f'تمت إضافة {added} سيرفرات بنجاح!', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/import_servers', methods=['POST'])
@login_required
def import_servers():
    if not request.is_admin:
        return "Unauthorized", 403
        
    subscription_text = request.form.get('subscription_text', '').strip()
    plan_months = int(request.form.get('plan_months') or 0)
    plan_days = int(request.form.get('plan_days') or 0)
    plan_hours = int(request.form.get('plan_hours') or 0)
    plan_minutes = int(request.form.get('plan_minutes') or 0)
    plan_seconds = int(request.form.get('plan_seconds') or 0)
    
    real_months = int(request.form.get('real_months') or 0)
    real_days = int(request.form.get('real_days') or 0)
    real_hours = int(request.form.get('real_hours') or 0)
    real_minutes = int(request.form.get('real_minutes') or 0)
    real_seconds = int(request.form.get('real_seconds') or 0)
    
    # Normalize mathematically
    total_plan_seconds = (plan_months * 30 * 24 * 3600) + (plan_days * 24 * 3600) + (plan_hours * 3600) + (plan_minutes * 60) + plan_seconds
    total_real_seconds = (real_months * 30 * 24 * 3600) + (real_days * 24 * 3600) + (real_hours * 3600) + (real_minutes * 60) + real_seconds
    
    price_base = request.form.get('price_base') or ''
    rule_tags = request.form.getlist('rule_tags[]')
    rule_prices = request.form.getlist('rule_prices[]')
    
    pricing_rules = []
    if True:
        for r_id, r_dict in get_all_pricing_rules().items():
            r = r_dict.copy()
            r['tags'] = set(r.get('tags', []))
            pricing_rules.append(r)

    # Strip happ://add/ if present
    if subscription_text.startswith('happ://add/'):
        subscription_text = subscription_text.replace('happ://add/', '')
    
    source_link_id = None
    original_url = subscription_text
    
    # If the text is a URL, fetch it
    if subscription_text.startswith('http://') or subscription_text.startswith('https://'):
        try:
            # Reuse an existing source link with the same URL instead of duplicating it
            existing_link = None
            for d in db.collection('source_links').where('url', '==', original_url).limit(1).stream():
                existing_link = d
            if existing_link is not None:
                source_link_id = existing_link.id
                db.collection('source_links').document(source_link_id).update({
                    'total_plan_seconds': total_plan_seconds,
                    'total_real_seconds': total_real_seconds
                })
            else:
                doc_ref = db.collection('source_links').add({
                    'url': original_url,
                    'total_plan_seconds': total_plan_seconds,
                    'total_real_seconds': total_real_seconds,
                    'created_at': datetime.now(timezone.utc)
                })
                source_link_id = doc_ref[1].id

            if not is_safe_url(subscription_text):
                flash('رابط الاستيراد المرفق غير آمن أو يستهدف عناوين محلية محظورة.', 'error')
                return redirect(url_for('admin.admin_dashboard'))

            resp = requests.get(subscription_text, timeout=10, headers={'User-Agent': 'v2rayNG'})
            if resp.status_code == 200:
                subscription_text = resp.text
            else:
                flash(f'فشل جلب الرابط، الكود: {resp.status_code}', 'error')
                return redirect(url_for('admin.admin_dashboard'))
        except Exception as e:
            flash(f'حدث خطأ أثناء جلب الرابط: {e}', 'error')
            return redirect(url_for('admin.admin_dashboard'))
            
    # Parse and add servers (shared with the per-link Sync flow)
    found, added = _import_vless_servers(
        subscription_text, total_plan_seconds, total_real_seconds,
        plan_days, plan_minutes, price_base, pricing_rules, source_link_id
    )

    if found == 0:
        flash('لم يتم العثور على سيرفرات VLESS صالحة في الرابط أو النص.', 'error')
        return redirect(url_for('admin.admin_dashboard'))

    flash(f'تمت إضافة {added} سيرفرات VLESS مستوردة بنجاح!', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/edit_server/<server_id>', methods=['POST'])
@login_required
def edit_server(server_id):
    if not request.is_admin: return "Unauthorized", 403
    new_name = request.form.get('name')
    new_price = request.form.get('price')
    if new_name:
        try:
            update_data = {'name': new_name}
            if new_price is not None:
                update_data['price'] = new_price
                
            new_plan_minutes = request.form.get('plan_minutes_input')
            if new_plan_minutes:
                try:
                    update_data['total_plan_seconds'] = int(new_plan_minutes) * 60
                except ValueError:
                    pass
                    
            new_expires_minutes = request.form.get('expires_minutes_input')
            if new_expires_minutes:
                try:
                    mins = int(new_expires_minutes)
                    update_data['expires_at'] = datetime.now(timezone.utc) + timedelta(minutes=mins)
                except ValueError:
                    pass
                
            db.collection('servers').document(server_id).update(update_data)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success'})
            flash('تم التعديل بنجاح', 'success')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': str(e)}), 400
            flash(f'خطأ أثناء التعديل: السيرفر غير موجود أو محذوف.', 'error')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Name is required'}), 400

    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/delete_server/<server_id>', methods=['POST'])
@login_required
def delete_server(server_id):
    if not request.is_admin: return "Unauthorized", 403
        
    db.collection('servers').document(server_id).delete()
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    
    flash('تم حذف السيرفر وجدولة نقل مستخدميه تلقائياً', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/approve_request/<request_id>', methods=['POST'])
@login_required
def approve_request(request_id):
    if not request.is_admin: return "Unauthorized", 403
    
    success, msg = _approve_request_logic(request_id)
    if success:
        flash('تم الموافقة على الطلب وإنشاء الاشتراك بنجاح / Request approved successfully', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/reject_request/<request_id>', methods=['POST'])
@login_required
def reject_request(request_id):
    if not request.is_admin: return "Unauthorized", 403
    
    success, msg = _reject_request_logic(request_id)
    if success:
        flash('تم رفض الطلب بنجاح / Request rejected successfully', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/delete_user/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not request.is_admin: return "Unauthorized", 403
    
    # 1. Delete all subscriptions and their DNS records
    subs = db.collection('subscriptions').where('user_id', '==', user_id).stream()
    for sub_doc in subs:
        db.collection('subscriptions').document(sub_doc.id).delete()
        
    # 2. Delete all purchase requests
    reqs = db.collection('purchase_requests').where('user_id', '==', user_id).stream()
    for req_doc in reqs:
        db.collection('purchase_requests').document(req_doc.id).delete()
        
    # 3. Delete all messages
    msgs = db.collection('messages').where('user_id', '==', user_id).stream()
    for msg_doc in msgs:
        db.collection('messages').document(msg_doc.id).delete()

    # 4. Delete the user document
    db.collection('users').document(user_id).delete()
    
    # 5. Delete from Firebase Auth
    try:
        firebase_auth.delete_user(user_id)
    except Exception as e:
        print(f"Error deleting user from Firebase Auth: {e}")
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
        
    flash('تم حذف المستخدم وجميع بياناته نهائياً / User and all data deleted completely', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/manage_subscription/<sub_id>', methods=['POST'])
@login_required
def manage_subscription(sub_id):
    if not request.is_admin: return "Unauthorized", 403
    action = request.form.get('action')
    
    sub_doc = db.collection('subscriptions').document(sub_id).get()
    if not sub_doc.exists: return redirect(url_for('admin.admin_dashboard'))
    data = sub_doc.to_dict()
    user_id = data.get('user_id')
    user_doc = db.collection('users').document(user_id).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    
    if action == 'cancel':
        update_data = {'status': 'expired'}
        if data.get('allocated_subdomain'):
            update_data['allocated_subdomain'] = None
            update_data['server_id'] = None
        db.collection('subscriptions').document(sub_id).update(update_data)
        flash('تم إلغاء الاشتراك بنجاح / Subscription cancelled', 'success')
        
    elif action == 'delete':
        db.collection('subscriptions').document(sub_id).delete()
        flash('تم حذف الاشتراك نهائياً / Subscription deleted permanently', 'success')
        
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
                
                old_subdomain = data.get('allocated_subdomain')
                if data.get('server_id') != server_id:
                    db.collection('subscriptions').document(sub_id).update({
                    'server_id': server_id,
                    'allocated_subdomain': None,
                    'status': 'active'
                })
                flash('تم تعيين السيرفر للاشتراك بنجاح / Server assigned to subscription', 'success')
                
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/manage_user_sub/<user_id>', methods=['POST'])
@login_required
def manage_user_sub(user_id):
    if not request.is_admin: return "Unauthorized", 403
    action = request.form.get('action')
    sub_id = request.form.get('sub_id')
    
    if sub_id:
        return manage_subscription(sub_id)
        
    if action == 'assign':
        server_id = request.form.get('server_id')
        if server_id:
            s_doc = db.collection('servers').document(server_id).get()
            if s_doc.exists:
                user_doc = db.collection('users').document(user_id).get()
                user_data = user_doc.to_dict() if user_doc.exists else {}
                
                new_sub_ref = db.collection('subscriptions').document()
                sub_id_new = new_sub_ref.id
                
                s_data = s_doc.to_dict()
                email_val = user_data.get('email', f'user-{user_id}')
                
                
                plan_days = int(s_data.get('plan_days', 0))
                plan_hours = int(s_data.get('plan_hours', 0))
                plan_minutes = int(s_data.get('plan_minutes', 0))
                duration = timedelta(days=plan_days, hours=plan_hours, minutes=plan_minutes)
                
                new_sub_ref.set({
                    'user_id': user_id,
                    'server_id': server_id,
                    'allocated_subdomain': None,
                    'status': 'active',
                    'created_at': datetime.now(timezone.utc),
                    'expires_at': datetime.now(timezone.utc) + duration
                })
                flash('تم تعيين السيرفر كمشترك جديد بنجاح / New subscription assigned', 'success')
                
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/send_message/<user_id>', methods=['POST'])
@login_required
def send_admin_message(user_id):
    if not request.is_admin: return jsonify({"error": "Unauthorized"}), 403
    
    # Support both JSON and Form Data
    message = request.json.get('message') if request.is_json else request.form.get('message')
    image_data = request.json.get('image') if request.is_json else request.form.get('image')
    
    if (not message or not message.strip()) and not image_data:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'status': 'error', 'error': 'Message cannot be empty'}), 400
        flash('Message cannot be empty', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    dt_now = datetime.now(timezone.utc)
    doc_data = {
        'user_id': user_id,
        'message': message.strip() if message else '',
        'created_at': dt_now,
        'is_read': False
    }
    if image_data:
        doc_data['image'] = image_data
        
    db.collection('admin_messages').add(doc_data)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'status': 'success',
            'chat_message': {
                'sender': 'admin',
                'text': message.strip() if message else '',
                'image': image_data if image_data else None,
                'timestamp': dt_now.strftime('%Y-%m-%d %H:%M')
            }
        })
        
    flash('تم إرسال الرسالة للمستخدم / Message sent', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/api/chat/<user_id>', methods=['GET'])
@login_required
def get_user_chat(user_id):
    if not getattr(request, 'is_admin', False) and request.user.get('uid') != user_id:
        return jsonify({"error": "Unauthorized"}), 403
    
    chat = []
    
    try:
        # Get user -> admin messages
        msgs = db.collection('messages').where('user_id', '==', user_id).stream()
        for m in msgs:
            data = m.to_dict()
            dt = data.get('created_at')
            if dt:
                chat.append({
                    'sender': 'user',
                    'text': data.get('message', ''),
                    'image': data.get('image', None),
                    'timestamp': dt.strftime('%Y-%m-%d %H:%M'),
                    '_dt': dt
                })
            # Also capture old admin replies stored within the same ticket
            admin_reply = data.get('admin_reply')
            if admin_reply and dt:
                chat.append({
                    'sender': 'admin',
                    'text': admin_reply,
                    'timestamp': dt.strftime('%Y-%m-%d %H:%M'),
                    '_dt': dt + timedelta(seconds=1) # artificially offset slightly
                })
                
        # Get admin -> user messages
        admin_msgs = db.collection('admin_messages').where('user_id', '==', user_id).stream()
        for am in admin_msgs:
            data = am.to_dict()
            dt = data.get('created_at')
            if dt:
                chat.append({
                    'sender': 'admin',
                    'text': data.get('message', ''),
                    'image': data.get('image', None),
                    'timestamp': dt.strftime('%Y-%m-%d %H:%M'),
                    '_dt': dt
                })
                
        # Sort by datetime
        chat.sort(key=lambda x: x['_dt'])
        
        # Remove the sort key
        for c in chat:
            del c['_dt']
            
        return jsonify({'status': 'success', 'chat': chat})
    except Exception as e:
        print(f"Error fetching chat for {user_id}: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@admin_bp.route('/read_admin_message/<msg_id>', methods=['POST'])
@login_required
def read_admin_message(msg_id):
    user_id = request.user['uid']
    doc = db.collection('admin_messages').document(msg_id).get()
    if doc.exists and doc.to_dict().get('user_id') == user_id:
        db.collection('admin_messages').document(msg_id).update({'is_read': True})
    return jsonify({'success': True})

@admin_bp.route('/admin/api/delete_chat/<user_id>', methods=['POST'])
@login_required
def delete_chat(user_id):
    if not getattr(request, 'is_admin', False): return jsonify({"error": "Unauthorized"}), 403
    try:
        # Delete user -> admin messages
        msgs = db.collection('messages').where('user_id', '==', user_id).stream()
        for msg in msgs:
            db.collection('messages').document(msg.id).delete()
            
        # Delete admin -> user messages
        admin_msgs = db.collection('admin_messages').where('user_id', '==', user_id).stream()
        for am in admin_msgs:
            db.collection('admin_messages').document(am.id).delete()
            
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@admin_bp.route('/admin/support', methods=['GET'])
@login_required
def admin_support():
    if not getattr(request, 'is_admin', False): return "Unauthorized", 403
    
    # Fetch all unique users who have a chat history
    conversations = {}
    
    try:
        msgs = db.collection('messages').stream()
        for m in msgs:
            d = m.to_dict()
            uid = d.get('user_id')
            if uid:
                if uid not in conversations:
                    conversations[uid] = {'email': d.get('email', 'Unknown'), 'last_msg': d.get('created_at', datetime.min), 'user_id': uid}
                elif d.get('created_at') and d['created_at'] > conversations[uid]['last_msg']:
                    conversations[uid]['last_msg'] = d['created_at']
                    
        admin_msgs = db.collection('admin_messages').stream()
        for am in admin_msgs:
            d = am.to_dict()
            uid = d.get('user_id')
            if uid:
                if uid not in conversations:
                    # Fetch email from users collection
                    try:
                        u_doc = db.collection('users').document(uid).get()
                        email = u_doc.to_dict().get('email', 'Unknown') if u_doc.exists else 'Unknown'
                    except:
                        email = 'Unknown'
                    conversations[uid] = {'email': email, 'last_msg': d.get('created_at', datetime.min), 'user_id': uid}
                elif d.get('created_at') and d['created_at'] > conversations[uid]['last_msg']:
                    conversations[uid]['last_msg'] = d['created_at']
                    
    except Exception as e:
        print("Error fetching conversations:", e)
        
    sorted_convs = sorted(list(conversations.values()), key=lambda x: x['last_msg'], reverse=True)
    return render_template('admin_support.html', conversations=sorted_convs, now=datetime.now(timezone.utc))

@admin_bp.route('/admin/delete_message/<message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    if not request.is_admin:
        return "Unauthorized", 403
    db.collection('messages').document(message_id).delete()
    flash('تم حذف الرسالة بنجاح / Message deleted', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/reply_message/<message_id>', methods=['POST'])
@login_required
def reply_message(message_id):
    if not request.is_admin:
        return "Unauthorized", 403
        
    reply_text = request.form.get('reply')
    if reply_text:
        db.collection('messages').document(message_id).update({
            'admin_reply': reply_text,
            'reply_at': datetime.now(timezone.utc)
        })
        flash('تم إرسال الرد بنجاح', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/migrate-db-once')
def migrate_db_once():
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
                
    return f"Migrated {subs_count} active subscriptions and {reqs_count} pending requests."

