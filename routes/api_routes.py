
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, current_app
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
import json
import uuid
import requests
from firebase_admin import firestore
from extensions import db, limiter, login_required, FIREBASE_READY, sub_serializer
from db_helpers import get_all_users, get_all_servers, get_all_messages, get_all_subscriptions, get_all_pricing_rules, get_all_source_links
from utils import extract_ip_from_json, modify_json_address, extract_name_from_json, generate_vless_uri, generate_full_config
from vless_parser import extract_vless_from_text
import urllib.parse
import socket
import ipaddress
import threading
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from helpers import *
from helpers import _approve_request_logic, _reject_request_logic, _import_vless_servers

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/available_servers')
@login_required
def api_available_servers():
    servers = []
    for doc in db.collection('servers').stream():
        s = doc.to_dict()
        s['id'] = doc.id
        # Clean non-serializable fields
        if 'expires_at' in s and s['expires_at']:
            s['expires_at'] = s['expires_at'].isoformat() + 'Z'
        if 'created_at' in s and s['created_at']:
            s['created_at'] = s['created_at'].isoformat() + 'Z'
        servers.append(s)
    return jsonify(servers)

@api_bp.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if not update:
        return "OK", 200
        
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if 'callback_query' in update:
        callback = update['callback_query']
        data = callback.get('data', '')
        message = callback.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        
        if data.startswith('approve_') or data.startswith('reject_'):
            action, req_id = data.split('_', 1)
            
            success = False
            result_text = ""
            
            try:
                if action == 'approve':
                    success, msg_text = _approve_request_logic(req_id)
                    result_text = "✅ Approved by Admin via Telegram" if success else f"❌ Failed: {msg_text}"
                elif action == 'reject':
                    success, msg_text = _reject_request_logic(req_id)
                    result_text = "❌ Rejected by Admin via Telegram" if success else f"❌ Failed: {msg_text}"
                    
                if success and chat_id and message_id and bot_token:
                    # Remove buttons and append result
                    original_caption = message.get('caption', '')
                    new_caption = f"{original_caption}\n\n{result_text}"
                    
                    url = f"https://api.telegram.org/bot{bot_token}/editMessageCaption"
                    requests.post(url, json={
                        'chat_id': chat_id,
                        'message_id': message_id,
                        'caption': new_caption,
                        'reply_markup': {'inline_keyboard': []} # Remove buttons
                    }, timeout=10)
                    
                # Answer callback to remove loading state
                requests.post(f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery", json={
                    'callback_query_id': callback.get('id'),
                    'text': result_text if success else "Action failed or already processed."
                }, timeout=10)
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"Webhook Error: {error_trace}")
                try:
                    with open(os.path.join(current_app.root_path, 'bomba_error.log'), 'a', encoding='utf-8') as f:
                        f.write(f"WEBHOOK EXCEPTION:\n{error_trace}\n")
                    # Try to answer the callback with the error
                    requests.post(f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery", json={
                        'callback_query_id': callback.get('id'),
                        'text': f"Error: {str(e)[:50]}"
                    }, timeout=10)
                except:
                    pass
                return "Error", 500
                
    return "OK", 200

@api_bp.route('/api/admin/setup_telegram', methods=['POST'])
@login_required
def setup_telegram_webhook():
    if not request.is_admin: return "Unauthorized", 403
    
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return jsonify({'status': 'error', 'error': 'Bot token not set'}), 400
        
    webhook_url = request.url_root.rstrip('/') + url_for('api.telegram_webhook')
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    
    try:
        resp = requests.post(url, json={'url': webhook_url}, timeout=10)
        data = resp.json()
        if data.get('ok'):
            return jsonify({'status': 'success', 'message': f'Webhook set to {webhook_url}'})
        else:
            return jsonify({'status': 'error', 'error': data.get('description')}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@api_bp.route('/api/admin/dashboard_sync')
@login_required
def api_dashboard_sync():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    now = datetime.now(timezone.utc)
    
    servers_list = []
    if True:
        for s_id, s_dict in get_all_servers().items():
            s = s_dict.copy()
            s['id'] = s_id
            if s.get('expires_at') and isinstance(s['expires_at'], datetime):
                s['expires_at'] = s['expires_at']
            servers_list.append(s)
            
    server_stats = {
        'total': len(servers_list),
        'gemini': sum(1 for s in servers_list if 'gemini' in [t.lower() for t in s.get('tags', [])]),
        'yt': sum(1 for s in servers_list if 'yt' in [t.lower() for t in s.get('tags', [])]),
        'lte': sum(1 for s in servers_list if 'lte' in [t.lower() for t in s.get('tags', [])]),
        'ru': sum(1 for s in servers_list if 'ru' in [t.lower() for t in s.get('tags', [])]),
        'torrent': sum(1 for s in servers_list if 'torrent' in [t.lower() for t in s.get('tags', [])])
    }
    
    users_dict = {}
    all_users = []
    active_users = []
    
    if True:
        for u_id, u_dict in get_all_users().items():
            u = u_dict.copy()
            u['id'] = u_id
            if u.get('created_at') and isinstance(u['created_at'], datetime):
                u['created_at'] = u['created_at']
            u['subscriptions'] = []
            users_dict[u_id] = u
            all_users.append(u)
            
    server_map = {s['id']: s.get('name') for s in servers_list}
    
    if True:
        for sub_id, sub_dict in get_all_subscriptions().items():
            sub = sub_dict.copy()
            sub['id'] = sub_id
            if sub.get('expires_at') and isinstance(sub['expires_at'], datetime):
                sub['expires_at'] = sub['expires_at']
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
    if True:
        for m_id, m_dict in get_all_messages().items():
            msg = m_dict.copy()
            msg['id'] = m_id
            if msg.get('created_at') and isinstance(msg['created_at'], datetime):
                msg['created_at'] = msg['created_at']
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
                    
    # Fetch source links, grouping any duplicates (same URL) into a single entry
    source_links_list = []
    try:
        docs_by_url = {}
        for doc in db.collection('source_links').stream():
            d = doc.to_dict()
            d['id'] = doc.id
            if d.get('created_at') and isinstance(d['created_at'], datetime):
                d['created_at'] = d['created_at']
            docs_by_url.setdefault(d.get('url', ''), []).append(d)

        for url, docs in docs_by_url.items():
            ids = {d['id'] for d in docs}
            linked_servers = [s for s in servers_list if s.get('source_link_id') in ids]
            # Representative doc: the one with the most linked servers (so Sync targets the live record)
            rep = max(docs, key=lambda d: sum(1 for s in servers_list if s.get('source_link_id') == d['id']))
            source_links_list.append({
                'id': rep['id'],
                'url': url,
                'created_at': rep.get('created_at'),
                'server_count': len(linked_servers),
                'servers': [{'id': s['id'], 'name': s.get('name', ''), 'country_code': s.get('country_code', '')} for s in linked_servers],
            })
    except Exception as e:
        print(f"Error fetching source_links: {e}")
    
    payload = {
        'server_stats': server_stats,
        'all_users': all_users,
        'active_users': active_users,
        'servers': servers_list,
        'tickets': tickets,
        'source_links': source_links_list
    }
    serialize_dates(payload)
    
    return jsonify(payload)

@api_bp.route('/api/admin/pricing_rules', methods=['GET', 'POST'])
@login_required
def api_pricing_rules():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    if request.method == 'GET':
        rules = []
        if True:
            for r_id, r_dict in get_all_pricing_rules().items():
                r = r_dict.copy()
                r['id'] = r_id
                # convert sets or arrays
                if 'tags' in r and isinstance(r['tags'], set):
                    r['tags'] = list(r['tags'])
                rules.append(r)
        return jsonify({'rules': rules})
        
    if request.method == 'POST':
        tags_str = request.form.get('tags', '')
        duration_months = int(request.form.get('duration_months') or 0)
        duration_days = int(request.form.get('duration_days') or 0)
        duration_hours = int(request.form.get('duration_hours') or 0)
        duration_minutes = int(request.form.get('duration_minutes') or 0)
        duration_seconds = int(request.form.get('duration_seconds') or 0)
        
        total_duration_seconds = (duration_months * 30 * 24 * 3600) + (duration_days * 24 * 3600) + (duration_hours * 3600) + (duration_minutes * 60) + duration_seconds
        
        price = float(request.form.get('price') or 0)
        
        tags_list = [tag.strip().lower() for tag in tags_str.split(',') if tag.strip()]
        
        db.collection('pricing_rules').add({
            'tags': tags_list,
            'duration_days': duration_days,
            'total_duration_seconds': total_duration_seconds,
            'price': price,
            'created_at': datetime.now(timezone.utc)
        })
        
        # If AJAX, return json. Otherwise redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'success'})
        return redirect(url_for('admin.admin_dashboard'))

@api_bp.route('/api/admin/pricing_rules/<rule_id>/delete', methods=['POST'])
@login_required
def delete_pricing_rule(rule_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    db.collection('pricing_rules').document(rule_id).delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    return redirect(url_for('admin.admin_dashboard'))

@api_bp.route('/api/admin/rescan_servers', methods=['POST'])
@login_required
def rescan_servers():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    # Get all rules
    rules = []
    if True:
        for r_id, r_dict in get_all_pricing_rules().items():
            r = r_dict.copy()
            # tags might be stored as list in firestore
            r['tags'] = set(r.get('tags', []))
            rules.append(r)
            
    # Iterate all active servers
    updated_count = 0
    if True:
        server_list = list(get_all_servers().items())
        
    for s_id, s_dict in server_list:
        name = s_dict.get('name', '').lower()
        plan_days = s_dict.get('plan_days', 0)
        
        # Re-extract tags
        new_tags = []
        name_no_dash = name.replace('-', ' ').replace('_', ' ').replace('|', ' ')
        words = name_no_dash.split()
        
        if 'gemini' in name: new_tags.append('gemini')
        if 'youtube' in name or 'yt' in words: new_tags.append('yt')
        if 'lte' in name: new_tags.append('lte')
        if 'russia' in name or 'ru' in words: new_tags.append('ru')
        if 'torrent' in name: new_tags.append('torrent')
        
        new_tags_set = set(new_tags)
        
        # Determine price based on rules
        final_price = s_dict.get('price', 0)
        
        matched_rules = []
        for rule in rules:
            # Handle old and new schema
            rule_secs = rule.get('total_duration_seconds')
            if rule_secs is None:
                rule_secs = rule.get('duration_days', 0) * 24 * 3600
                
            server_plan_secs = s_dict.get('total_plan_seconds')
            if server_plan_secs is None:
                server_plan_secs = (s_dict.get('plan_days', 0) * 24 * 3600) + (s_dict.get('plan_hours', 0) * 3600) + (s_dict.get('plan_minutes', 0) * 60)
                
            tags_match = False
            if not rule['tags'] and not new_tags_set:
                tags_match = True
            elif rule['tags'] and rule['tags'].issubset(new_tags_set):
                tags_match = True
                
            if tags_match and rule_secs == server_plan_secs:
                matched_rules.append(rule)
                
        if matched_rules:
            # Most specific tags match wins
            best_rule = max(matched_rules, key=lambda r: len(r['tags']))
            final_price = best_rule['price']
            
        # Update server in DB
        db.collection('servers').document(s_id).update({
            'tags': new_tags,
            'price': final_price
        })
        updated_count += 1
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'updated': updated_count})
    flash(f'تم تحديث {updated_count} سيرفرات بنجاح.', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@api_bp.route('/api/admin/sync_link/<link_id>', methods=['POST'])
@login_required
def sync_link(link_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    # Load the saved source link
    try:
        doc = db.collection('source_links').document(link_id).get()
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    if not doc.exists:
        return jsonify({'status': 'error', 'message': 'الرابط غير موجود'}), 404

    link = doc.to_dict()
    url = link.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'لا يوجد رابط محفوظ'}), 400

    total_plan_seconds = link.get('total_plan_seconds', 0) or 0
    total_real_seconds = link.get('total_real_seconds', 0) or 0

    if not is_safe_url(url):
        return jsonify({'status': 'error', 'message': 'الرابط غير آمن أو يستهدف شبكة محلية.'}), 400

    # Re-fetch the subscription content from the saved URL
    try:
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'v2rayNG'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'فشل جلب الرابط: {e}'}), 400

    if resp.status_code != 200:
        return jsonify({'status': 'error', 'message': f'فشل جلب الرابط، الكود: {resp.status_code}'}), 400

    pricing_rules = []
    if True:
        for r_id, r_dict in get_all_pricing_rules().items():
            r = r_dict.copy()
            r['tags'] = set(r.get('tags', []))
            pricing_rules.append(r)

    plan_days = total_plan_seconds // (24 * 3600)

    found, added = _import_vless_servers(
        resp.text, total_plan_seconds, total_real_seconds,
        plan_days, 0, '', pricing_rules, link_id, dedup=True
    )

    return jsonify({'status': 'success', 'found': found, 'added': added})

@api_bp.route('/api/admin/delete_source_link/<link_id>', methods=['POST'])
@login_required
def delete_source_link(link_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    try:
        # Resolve every source_links doc sharing this link's URL (covers old duplicates)
        target_ids = [link_id]
        doc = db.collection('source_links').document(link_id).get()
        if doc.exists:
            url = doc.to_dict().get('url')
            if url:
                target_ids = [d.id for d in db.collection('source_links').where('url', '==', url).stream()]
                if link_id not in target_ids:
                    target_ids.append(link_id)

        for lid in target_ids:
            # Detach the link from any servers that reference it (keep the servers)
            for s in db.collection('servers').where('source_link_id', '==', lid).stream():
                db.collection('servers').document(s.id).update({'source_link_id': None})
            db.collection('source_links').document(lid).delete()
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

    return jsonify({'status': 'success'})

@api_bp.route('/api/admin/debts_sync')
@login_required
def api_debts_sync():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    now = datetime.now(timezone.utc)
    in_debt_users = []
    
    servers_map = {}
    if True:
        for s_id, s_dict in get_all_servers().items():
            servers_map[s_id] = s_dict.copy()
            
    if True:
        for sub_id, sub_dict in get_all_subscriptions().items():
            if sub_dict.get('status') == 'active':
                server_id = sub_dict.get('server_id')
                sub_exp = sub_dict.get('expires_at')
                if not server_id or not sub_exp:
                    continue
                if isinstance(sub_exp, datetime):
                    sub_exp = sub_exp
                    
                s_data = servers_map.get(server_id)
                if not s_data: continue
                s_exp = s_data.get('expires_at')
                if not s_exp: continue
                if isinstance(s_exp, datetime):
                    s_exp = s_exp
                    
                if s_exp < sub_exp:
                    delta = sub_exp - s_exp
                    user_id = sub_dict.get('user_id')
                    u_email = "Unknown"
                    if True:
                        if user_id in get_all_users():
                            u_email = get_all_users()[user_id].get('email', 'Unknown')
                            
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

@api_bp.route('/api/admin/pending_requests')
@login_required
def api_pending_requests():
    if not getattr(request, 'is_admin', False):
        return "Unauthorized", 403
        
    requests_ref = db.collection('purchase_requests').where('status', '==', 'pending').stream()
    
    pending_list = []
    for doc in requests_ref:
        req = doc.to_dict()
        req['id'] = doc.id
        
        # Convert datetime objects to string
        for k, v in req.items():
            if isinstance(v, datetime):
                req[k] = v.isoformat()
        
        # Get server details
        if req.get('server_id'):
            s_doc = db.collection('servers').document(req['server_id']).get()
            if s_doc.exists:
                req['server'] = s_doc.to_dict()
                req['server']['id'] = s_doc.id
                
        # Get user details for the UI (like email, old stats)
        user_doc = db.collection('users').document(req['user_id']).get()
        if user_doc.exists:
            # We nest it inside 'user' to maintain compatibility if the UI expects flat or nested fields
            req['user'] = user_doc.to_dict()
            # Flatten email for easier access
            if 'email' not in req:
                req['email'] = req['user'].get('email')
                
        # For UI compatibility with old model (it expected receipt_image on user)
        req['receipt_image'] = req.get('receipt_url')
        
        pending_list.append(req)
        
    return jsonify(pending_list)

@api_bp.route('/api/admin/stats')
@login_required
def admin_stats():
    if not request.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        users = list(db.collection('users').stream())
        servers = list(db.collection('servers').stream())
        
        active_users = sum(1 for u in users if u.to_dict().get('status') == 'active')
        expired_users = len(users) - active_users
        
        total_debt = sum(float(u.to_dict().get('debt', 0)) for u in users)
        
        return jsonify({
            'users_active': active_users,
            'users_expired': expired_users,
            'servers_total': len(servers),
            'total_debt': total_debt
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/api/cron/daily', methods=['GET', 'POST'])
def cron_daily():
    # This endpoint should be triggered by cron-job.org once a day
    smtp_email = os.environ.get('SMTP_EMAIL')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    
    if not smtp_email or not smtp_password:
        return jsonify({'status': 'error', 'message': 'SMTP not configured'}), 400
        
    now = datetime.now(timezone.utc)
    reminder_threshold = now + timedelta(days=2) # 48 hours from now
    
    # Get all active subscriptions
    active_subs = db.collection('subscriptions').where('status', '==', 'active').stream()
    
    emails_sent = 0
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(smtp_email, smtp_password)
        
        for sub_doc in active_subs:
            sub = sub_doc.to_dict()
            expires_at = sub.get('expires_at')
            if not expires_at:
                continue
                
            # Make timezone naive
            if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
                expires_at = expires_at
                
            # If expiring within 48 hours but strictly in the future
            if now < expires_at <= reminder_threshold:
                # Check if reminder already sent recently
                last_sent = sub.get('reminder_sent_at')
                if last_sent:
                    if hasattr(last_sent, 'tzinfo') and last_sent.tzinfo is not None:
                        last_sent = last_sent
                    if (now - last_sent).days < 2:
                        continue # Already sent within the last 48 hours
                
                # Fetch user email
                user_id = sub.get('user_id')
                user_doc = db.collection('users').document(user_id).get()
                if user_doc.exists:
                    user_email = user_doc.to_dict().get('email')
                    if user_email:
                        # Construct email
                        msg = MIMEMultipart()
                        msg['From'] = smtp_email
                        msg['To'] = user_email
                        msg['Subject'] = "تذكير: اشتراكك في GalaxyVPN قارب على الانتهاء"
                        
                        body = f"""
                        أهلاً بك،
                        
                        نود تذكيرك بأن اشتراكك في GalaxyVPN سينتهي خلال أقل من 48 ساعة.
                        يرجى تجديد الاشتراك لتجنب انقطاع الخدمة.
                        
                        رابط التجديد: {request.host_url}pay
                        
                        مع تحيات فريق GalaxyVPN.
                        """
                        msg.attach(MIMEText(body, 'plain'))
                        
                        try:
                            server.send_message(msg)
                            db.collection('subscriptions').document(sub_doc.id).update({
                                'reminder_sent_at': now
                            })
                            emails_sent += 1
                        except Exception as e:
                            print(f"Failed to send email to {user_email}: {e}")
                            
        server.quit()
        return jsonify({'status': 'success', 'emails_sent': emails_sent})
        
    except Exception as e:
        print(f"SMTP error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

