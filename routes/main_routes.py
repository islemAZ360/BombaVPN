
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
from translations import TRANSLATIONS
from helpers import *

main_bp = Blueprint('main', __name__)

@main_bp.route('/set_language/<lang>')
def set_language(lang):
    if lang in TRANSLATIONS:
        resp = redirect(request.referrer or '/')
        resp.set_cookie('lang', lang, max_age=60*60*24*365, samesite='Lax')
        return resp
    return redirect('/')

@main_bp.route('/robots.txt')
def robots():
    content = f"User-agent: *\nDisallow: /admin/\nDisallow: /api/\nDisallow: /sub/\nSitemap: {request.url_root}sitemap.xml\n"
    return content, 200, {'Content-Type': 'text/plain'}

@main_bp.route('/sitemap.xml')
def sitemap():
    pages = ['/', '/login', '/register']
    base_url = request.url_root.rstrip('/')
    urls = ""
    for page in pages:
        urls += f"  <url>\n    <loc>{base_url}{page}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>{1.0 if page == '/' else 0.8}</priority>\n  </url>\n"
    
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>'
    return xml, 200, {'Content-Type': 'application/xml'}

@main_bp.route('/')
def index():
    session_cookie = request.cookies.get('session')
    if session_cookie:
        try:
            decoded = firebase_auth.verify_session_cookie(session_cookie)
            if decoded.get('email') == 'islamazaizia360@gmail.com':
                return redirect(url_for('admin.admin_dashboard'))
            return redirect(url_for('main.user_dashboard'))
        except:
            pass
    return render_template('index.html')

@main_bp.route('/debug-check')
def debug_check():
    return f"Server code v2 running OK at {datetime.now()}", 200

@main_bp.route('/pay', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")
def pay():
    user_id = request.user['uid']
    user_doc = db.collection('users').document(user_id).get()
    data = {}
    if user_doc.exists:
        data = user_doc.to_dict()
    servers = []
    now = datetime.now(timezone.utc)
    for doc in db.collection('servers').stream():
        s = doc.to_dict()
        s_exp = s.get('expires_at')
        if s_exp:
            if s_exp.tzinfo is None:
                s_exp = s_exp.replace(tzinfo=timezone.utc)
            s_exp = s_exp
            if s_exp > now:
                s['id'] = doc.id
                servers.append(s)
        else:
            s['id'] = doc.id
            servers.append(s)
        
    if request.method == 'POST':
        server_id = request.form.get('server_id')
        if not server_id:
            flash('الرجاء اختيار السيرفر / Please select a server', 'error')
            return redirect(request.url)
            
        if 'receipt' not in request.files:
            flash('لم يتم اختيار صورة الوصل', 'error')
            return redirect(request.url)
        file = request.files['receipt']
        if file.filename == '':
            flash('لم يتم اختيار صورة الوصل', 'error')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
            filename = f"receipt_{user_id}_{uuid.uuid4().hex[:8]}.{ext}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            
            # Save the new purchase request in the dedicated collection
            renew_sub_id = request.form.get('renew_sub_id')
            doc_ref = db.collection('purchase_requests').document()
            doc_ref.set({
                'user_id': user_id,
                'email': request.user.get('email', data.get('email', 'Unknown')),
                'server_id': server_id,
                'renew_sub_id': renew_sub_id,
                'receipt_url': filename,
                'status': 'pending',
                'created_at': datetime.now(timezone.utc)
            })
            
            # Fetch server name and price for telegram
            server_name = 'Unknown'
            price = 0
            s_doc = db.collection('servers').document(server_id).get()
            if s_doc.exists:
                server_name = s_doc.to_dict().get('name', 'Unknown')
                price = s_doc.to_dict().get('price', 0)
            
            # إرسال صورة الوصل لتيليجرام مع أزرار القبول والرفض
            req_id = doc_ref.id
            try:
                send_telegram_receipt_review(req_id, request.user.get('email', data.get('email', 'Unknown')), server_name, filename, price)
            except Exception as e:
                print(f"Error calling send_telegram_receipt_review: {e}")
            
            flash('تم إرسال الطلب بنجاح. جاري مراجعته من قبل الإدارة. / Request submitted successfully. Under review.', 'success')
            return redirect(url_for('main.user_dashboard'))
            
    return render_template('payment.html', servers=servers, user=request.user)

@main_bp.route('/dashboard')
@login_required
def user_dashboard():
    if request.is_admin:
        return redirect(url_for('admin.admin_dashboard'))
        
    user_id = request.user['uid']
    user_data = None
    
    if True:
        if user_id in get_all_users():
            user_data = get_all_users()[user_id].copy()

    if not user_data:
        try:
            user_doc = db.collection('users').document(user_id).get()
            if not user_doc.exists:
                try:
                    firebase_auth.get_user(user_id)
                    db.collection('users').document(user_id).set({
                        'email': request.user['email'],
                        'status': 'pending',
                        'created_at': datetime.now(timezone.utc),
                        'referral_code': user_id[:8]
                    })
                    user_data = {'status': 'pending', 'referral_code': user_id[:8]}
                except Exception as e:
                    # User was deleted from Firebase Auth (e.g. by admin)
                    response = make_response(redirect(url_for('auth.login')))
                    response.delete_cookie('session')
                    return response
            else:
                user_data = user_doc.to_dict()
                if 'referral_code' not in user_data:
                    user_data['referral_code'] = user_id[:8]
                    db.collection('users').document(user_id).update({'referral_code': user_id[:8]})
        except Exception as e:
            print(f"Error fetching user doc in dashboard: {e}")
            user_data = {'status': 'pending', 'error': 'db_quota', 'referral_code': user_id[:8]}

    subscriptions = []
    has_active = False
    try:
        server_map = {}
        if True:
            for s_id, s_dict in get_all_servers().items():
                server_map[s_id] = s_dict.get('name', 'Unknown')
                
        for doc in db.collection('subscriptions').where('user_id', '==', user_id).stream():
            sub = doc.to_dict()
            sub['id'] = doc.id
            if 'expires_at' in sub and sub['expires_at']:
                if isinstance(sub['expires_at'], datetime):
                    sub['expires_at'] = sub['expires_at']
            
            if sub.get('server_id'):
                if sub['server_id'] in server_map:
                    sub['allocated_server_name'] = server_map[sub['server_id']]
                else:
                    s_doc = db.collection('servers').document(sub['server_id']).get()
                    if s_doc.exists:
                        s_data = s_doc.to_dict()
                        sub['allocated_server_name'] = s_data.get('name', 'Unknown')
                        server_map[sub['server_id']] = sub['allocated_server_name']
                    else:
                        sub['allocated_server_name'] = 'Unknown'
            else:
                sub['allocated_server_name'] = 'Unknown'
                
            if sub.get('status') == 'active':
                has_active = True
            subscriptions.append(sub)
            
        # Sort so active are first, and latest expiration is first
        subscriptions.sort(key=lambda x: (0 if x.get('status') == 'active' else 1, x.get('expires_at', datetime.min).timestamp() if isinstance(x.get('expires_at'), datetime) else 0))
    except Exception as e:
        print("Error fetching subscriptions:", e)
        
    try:
        reqs = []
        for doc in db.collection('purchase_requests').where('user_id', '==', user_id).stream():
            reqs.append(doc.to_dict())
        if reqs:
            reqs.sort(key=lambda x: x.get('created_at', datetime.min).timestamp() if isinstance(x.get('created_at'), datetime) else 0, reverse=True)
            user_data['latest_req'] = reqs[0]
    except Exception as e:
        print("Error fetching purchase requests:", e)
        
    user_data['status'] = 'active' if has_active else ('expired' if subscriptions else user_data.get('status', 'pending'))
            
    email = request.user['email']
    # Security fix: Sign the user_id so it cannot be tampered with or guessed
    secure_token = sub_serializer.dumps(user_id)
    sub_link = url_for('main.get_subscription', token=secure_token, _external=True)
    
    messages = []
    try:
        for doc in db.collection('messages').where('user_id', '==', user_id).stream():
            msg = doc.to_dict()
            msg['id'] = doc.id
            if 'created_at' in msg and msg['created_at']:
                msg['created_at'] = msg['created_at']
            else:
                msg['created_at'] = datetime.min
            messages.append(msg)
        messages.sort(key=lambda x: x.get('created_at', datetime.min))
    except Exception as e:
        print("Error fetching messages:", e)
        
    admin_msgs = []
    try:
        for doc in db.collection('admin_messages').where('user_id', '==', user_id).stream():
            msg = doc.to_dict()
            msg['id'] = doc.id
            if 'created_at' in msg and msg['created_at']:
                msg['created_at'] = msg['created_at']
            else:
                msg['created_at'] = datetime.min
            admin_msgs.append(msg)
        admin_msgs.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
    except Exception as e:
        print("Error fetching admin messages:", e)
        
    return render_template('user_dashboard.html', user_email=email, user=user_data, sub_link=sub_link, messages=messages, admin_msgs=admin_msgs, subscriptions=subscriptions, now=datetime.now(timezone.utc))

@main_bp.route('/api/message', methods=['POST'])
@login_required
def send_message():
    text = request.json.get('message') if request.is_json else request.form.get('message')
    image_data = request.json.get('image') if request.is_json else request.form.get('image')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    
    if text or image_data:
        dt_now = datetime.now(timezone.utc)
        
        doc_data = {
            'user_id': request.user['uid'],
            'email': request.user['email'],
            'message': text or '',
            'created_at': dt_now,
            'admin_reply': None
        }
        
        if image_data:
            doc_data['image'] = image_data
            
        db.collection('messages').add(doc_data)
        
        # إرسال إشعار تيليجرام
        msg_text = text if text else "[صورة مرفقة]"
        msg = f"💬 *رسالة دعم جديدة!*\nالمستخدم: `{request.user['email']}`\nالرسالة:\n{msg_text}"
        send_telegram_notification(msg)
        
        if is_ajax:
            return jsonify({
                'status': 'success', 
                'chat_message': {
                    'sender': 'user',
                    'text': text or '',
                    'image': image_data if image_data else None,
                    'timestamp': dt_now.strftime('%Y-%m-%d %H:%M')
                }
            }), 200
        flash('تم إرسال رسالتك بنجاح', 'success')
    return redirect(url_for('main.user_dashboard'))

@main_bp.route('/api/user_status')
@login_required
def api_user_status():
    user_id = request.user['uid']
    user_data = {}
    doc = db.collection('users').document(user_id).get()
    if doc.exists:
        user_data = doc.to_dict()
        
    subs = list(db.collection('subscriptions').where('user_id', '==', user_id).stream())
    has_active = any(sub.to_dict().get('status') == 'active' for sub in subs)
    
    computed_status = 'active' if has_active else ('expired' if subs else user_data.get('status', 'pending'))
    
    # Get latest active expiry if any
    expires_at = None
    if subs:
        active_subs = [s.to_dict() for s in subs if s.to_dict().get('status') == 'active']
        if active_subs:
            latest = max(active_subs, key=lambda x: x.get('expires_at', datetime.min).timestamp() if isinstance(x.get('expires_at'), datetime) else 0)
            if 'expires_at' in latest and isinstance(latest['expires_at'], datetime):
                expires_at = latest['expires_at'].isoformat()

    reqs = list(db.collection('purchase_requests').where('user_id', '==', user_id).stream())
    latest_req_status = ""
    if reqs:
        reqs.sort(key=lambda x: x.to_dict().get('created_at', datetime.min).timestamp() if isinstance(x.to_dict().get('created_at'), datetime) else 0, reverse=True)
        latest_req_status = reqs[0].to_dict().get('status', '')

    return jsonify({
        'status': computed_status,
        'latest_req_status': latest_req_status,
        'expires_at': expires_at or ""
    })

@main_bp.route('/sub/<token>')
def get_subscription(token):
    # Security fix: Verify the signed token
    try:
        user_id = sub_serializer.loads(token)
    except Exception:
        return "Invalid subscription token.", 403
        
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    user_agent = request.headers.get('User-Agent', '')
    
    try:
        db.collection('users').document(user_id).update({
            'accessed_ips': firestore.ArrayUnion([client_ip]),
            'accessed_devices': firestore.ArrayUnion([user_agent])
        })
    except Exception as e:
        print(f"Error tracking link access for {user_id}: {e}")
        
    subs_ref = db.collection('subscriptions').where('user_id', '==', user_id).stream()
    subs = list(subs_ref)
    
    combined_links = []
    has_active = False
    
    from utils import generate_vless_uri
    import re
    import base64
    from datetime import datetime, timezone
        
    now = datetime.now(timezone.utc)
    
    for sub_doc in subs:
        sub_data = sub_doc.to_dict()
        server_id = sub_data.get('server_id')
        subdomain = None
        status = sub_data.get('status')
        expires_at = sub_data.get('expires_at')
        
        is_expired = False
        if status == 'expired':
            is_expired = True
        elif expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                is_expired = True
                if status != 'expired':
                    db.collection('subscriptions').document(sub_doc.id).update({'status': 'expired'})
                
        if server_id:
            server_doc = db.collection('servers').document(server_id).get()
            if server_doc.exists:
                server = server_doc.to_dict()
                
                # Reverting back to original_ip because Dynv6 is blocked by ISPs
                if is_expired:
                    active_address = "127.0.0.1"
                else:
                    active_address = server.get('original_ip')
                    has_active = True
                
                vless_uri = None
                server_name = server.get('name', 'BombaVPN Server')
                import urllib.parse
                safe_name = urllib.parse.quote(server_name)
                
                if server.get('vless_link'):
                    vless_uri = re.sub(r'(@)([^:?#]+)', r'\g<1>' + active_address, server['vless_link'], count=1)
                    if '#' in vless_uri:
                        vless_uri = re.sub(r'#.*$', '#' + safe_name, vless_uri)
                    else:
                        vless_uri += '#' + safe_name
                elif server.get('json_config'):
                    vless_uri = generate_vless_uri(server['json_config'], active_address)
                    if vless_uri:
                        if '#' in vless_uri:
                            vless_uri = re.sub(r'#.*$', '#' + safe_name, vless_uri)
                        else:
                            vless_uri += '#' + safe_name
                    
                if vless_uri and not is_expired:
                    combined_links.append(vless_uri)

    if not has_active:
        poisoned_link = "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:80?type=tcp&security=none#❌_All_Subscriptions_Expired_-_Please_Renew"
        combined_links.insert(0, poisoned_link)
        
    if not combined_links:
        poisoned_link = "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:80?type=tcp&security=none#⚠️_No_Servers_Found"
        combined_links.append(poisoned_link)
        
    combined_text = "\n".join(combined_links)
    encoded_link = base64.b64encode(combined_text.encode('utf-8')).decode('utf-8')
    
    return encoded_link, 200, {
        'Content-Type': 'text/plain; charset=utf-8',
        'profile-update-interval': '1' if has_active else '0.25',
        'profile-web-page-url': 'https://bombavpn.onrender.com'
    }

@main_bp.route('/ping')
def ping():
    return "OK", 200

@main_bp.route('/bomba_logs_secret_1234')
def view_bomba_logs():
    try:
        with open(os.path.join(current_app.root_path, 'bomba_error.log'), 'r') as f:
            return "<pre>" + f.read() + "</pre>"
    except Exception as e:
        return str(e)
