
def parse_device_info(user_agent):
    if not user_agent: return "Unknown Device"
    ua = user_agent.lower()
    
    client = "Unknown Client"
    if 'v2rayng' in ua: client = 'v2rayNG'
    elif 'v2rayn' in ua: client = 'v2rayN'
    elif 'shadowrocket' in ua: client = 'Shadowrocket'
    elif 'streisand' in ua: client = 'Streisand'
    elif 'clash' in ua or 'clashforwindows' in ua or 'clashx' in ua: client = 'Clash'
    elif 'quantumult' in ua or 'quantumult%20x' in ua: client = 'Quantumult X'
    elif 'surge' in ua: client = 'Surge'
    elif 'loon' in ua: client = 'Loon'
    elif 'hiddify' in ua: client = 'Hiddify'
    elif 'nekoray' in ua or 'nekobox' in ua: client = 'NekoBox'
    elif 'fair%20vpn' in ua or 'fairvpn' in ua: client = 'Fair VPN'
    elif 'v2box' in ua: client = 'V2Box'
    elif 'v2ray tuning' in ua or 'v2raytun' in ua: client = 'V2Ray Tun'
    elif 'sing-box' in ua: client = 'sing-box'
    elif 'mozilla' in ua or 'chrome' in ua or 'safari' in ua:
        if 'edg/' in ua or 'edge' in ua: client = 'Edge'
        elif 'chrome' in ua: client = 'Chrome'
        elif 'firefox' in ua: client = 'Firefox'
        elif 'safari' in ua: client = 'Safari'
        else: client = 'Web Browser'
    elif 'dart' in ua: client = 'Flutter App'
    elif 'go-http-client' in ua: client = 'Go Client'
    elif 'cfnetwork' in ua: client = 'Apple CFNetwork'
    
    os_name = "Unknown OS"
    if 'android' in ua: os_name = 'Android'
    elif 'iphone' in ua or 'ipad' in ua or 'ios' in ua or 'cfnetwork' in ua or 'shadowrocket' in ua or 'quantumult' in ua: os_name = 'iOS'
    elif 'windows' in ua or 'win64' in ua or 'win32' in ua or 'v2rayn' in ua: os_name = 'Windows'
    elif 'mac os' in ua or 'macintosh' in ua: os_name = 'macOS'
    elif 'linux' in ua: os_name = 'Linux'
    
    if client == 'v2rayNG': os_name = 'Android'
    if client == 'v2rayN': os_name = 'Windows'
    if client == 'Shadowrocket': os_name = 'iOS'
    
    if os_name == "Unknown OS" and client == "Unknown Client":
        return user_agent[:30] + "..." if len(user_agent) > 30 else user_agent
        
    return f"{os_name} | {client}"


from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, current_app
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
import json
import uuid
import requests
from extensions import limiter, login_required, sub_serializer
from supabase_client import supabase_admin
from db_helpers import get_all_users, get_all_servers, get_all_messages, get_all_subscriptions, get_all_pricing_rules, get_all_source_links
from utils import extract_ip_from_json, modify_json_address, extract_name_from_json, generate_vless_uri, generate_full_config, parse_dt
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
            user_resp = supabase_admin.auth.get_user(session_cookie)
            decoded = {'email': user_resp.user.email} if user_resp and user_resp.user else {}
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
    user_resp = supabase_admin.table('users').select('*').eq('id', user_id).execute()
    user_doc = user_resp.data[0] if user_resp.data else None
    data = {}
    if user_doc:
        data = user_doc
    servers = []
    now = datetime.now(timezone.utc)
    for s in (supabase_admin.table('servers').select('*').execute().data or []):
        s_exp = s.get('expires_at')
        if s_exp:
            s_exp = parse_dt(s_exp)
            if s_exp and s_exp > now:
                servers.append(s)
        else:
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
            
            # Fetch server name and price first; the price is stored on the
            # request so admin revenue/analytics reflect the real amount.
            server_name = 'Unknown'
            price = 0
            s_resp = supabase_admin.table('servers').select('*').eq('id', server_id).execute()
            s_doc = s_resp.data[0] if s_resp.data else None
            if s_doc:
                server_name = s_doc.get('name', 'Unknown')
                price = s_doc.get('price', 0)

            # Save the new purchase request in the dedicated collection
            renew_sub_id = request.form.get('renew_sub_id')
            req_id = str(uuid.uuid4())
            try:
                supabase_admin.table('purchase_requests').insert({
                    'user_id': user_id,
                    'email': request.user.get('email', data.get('email', 'Unknown')),
                    'server_id': server_id,
                    'renew_sub_id': renew_sub_id,
                    'receipt_url': filename,
                    'price': str(price),
                    'status': 'pending',
                    'id': req_id,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }).execute()
            except Exception as e:
                import traceback; traceback.print_exc()
                flash(f'تعذّر حفظ الطلب / Could not save request: {e}', 'error')
                return redirect(request.url)

            # إرسال صورة الوصل لتيليجرام مع أزرار القبول والرفض
            
            user_email_str = request.user.get('email', data.get('email', 'Unknown'))
            app = current_app._get_current_object()
            try:
                def send_receipt(app_instance):
                    with app_instance.app_context():
                        try:
                            send_telegram_receipt_review(req_id, user_email_str, server_name, filename, price)
                        except Exception as inner_e:
                            print(f"Inner thread error sending telegram receipt: {inner_e}")
                
                threading.Thread(target=send_receipt, args=(app,), daemon=True).start()
            except Exception as e:
                print(f"Error starting thread for telegram receipt: {e}")
            
            from helpers import get_translation
            flash(get_translation('FlashReqSubmitted'), 'success')
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
            user_resp = supabase_admin.table('users').select('*').eq('id', user_id).execute()
            user_doc = user_resp.data[0] if user_resp.data else None
            if not user_doc:
                try:
                    user_auth_resp = supabase_admin.auth.admin.get_user_by_id(user_id)
                    supabase_admin.table('users').insert({
                        'email': request.user['email'],
                        'status': 'pending',
                        'created_at': datetime.now(timezone.utc),
                        'id': user_id,
                        'referral_code': user_id[:8]
                    }).execute()
                    user_data = {'status': 'pending', 'referral_code': user_id[:8]}
                except Exception as e:
                    # User was deleted from Firebase Auth (e.g. by admin)
                    response = make_response(redirect(url_for('auth.login')))
                    response.delete_cookie('session')
                    return response
            else:
                user_data = user_doc
                if 'referral_code' not in user_data:
                    user_data['referral_code'] = user_id[:8]
                    supabase_admin.table('users').update({'referral_code': user_id[:8]}).eq('id', user_id).execute()
        except Exception as e:
            print(f"Error fetching user doc in dashboard: {e}")
            user_data = {'status': 'pending', 'error': 'db_quota', 'referral_code': user_id[:8]}

    subscriptions = []
    has_active = False
    try:
        server_map = {}
        if True:
            for s_id, s_dict in get_all_servers().items():
                server_map[s_id] = s_dict
                
        for sub in (supabase_admin.table('subscriptions').select('*').eq('user_id', user_id).execute().data or []):
            if 'expires_at' in sub and sub['expires_at']:
                sub['expires_at'] = parse_dt(sub['expires_at'])
            
            if sub.get('server_id'):
                s_data = None
                if sub['server_id'] in server_map:
                    s_data = server_map[sub['server_id']]
                else:
                    s_resp = supabase_admin.table('servers').select('*').eq('id', sub['server_id']).execute()
                    s_doc = s_resp.data[0] if s_resp.data else None
                    if s_doc:
                        s_data = s_doc
                        server_map[sub['server_id']] = s_data
                        
                if s_data:
                    s_name = s_data.get('name', 'Unknown')
                    c_code = s_data.get('country_code', '').upper()
                    
                    # Instead of an emoji that breaks on Windows, pass the country code
                    # to the frontend to render an SVG flag from flagcdn
                    sub['allocated_server_name'] = s_name
                    if c_code and len(c_code) == 2:
                        sub['allocated_server_country'] = c_code.lower()
                    else:
                        sub['allocated_server_country'] = None
                else:
                    sub['allocated_server_name'] = 'Unknown'
            else:
                sub['allocated_server_name'] = 'Unknown'
                
            if sub.get('status') == 'active':
                has_active = True
            subscriptions.append(sub)
            
        # Sort so active are first, and latest expiration is first
        subscriptions.sort(key=lambda x: (0 if x.get('status') == 'active' else 1, parse_dt(x.get('expires_at')).timestamp() if parse_dt(x.get('expires_at')) else 0))
    except Exception as e:
        print("Error fetching subscriptions:", e)
        
    try:
        reqs = []
        reqs = supabase_admin.table('purchase_requests').select('*').eq('user_id', user_id).execute().data or []
        if reqs:
            reqs.sort(key=lambda x: parse_dt(x.get('created_at')).timestamp() if x.get('created_at') else 0, reverse=True)
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
        for msg in (supabase_admin.table('messages').select('*').eq('user_id', user_id).execute().data or []):
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
        for msg in (supabase_admin.table('admin_messages').select('*').eq('user_id', user_id).execute().data or []):
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
            if not image_data.startswith('data:image/'):
                if is_ajax:
                    return jsonify({'status': 'error', 'error': 'Invalid image format'}), 400
                flash('Invalid image format', 'danger')
                return redirect(url_for('main.user_dashboard'))
            doc_data['image'] = image_data
            
        doc_data['id'] = str(uuid.uuid4())
        doc_data['created_at'] = doc_data['created_at'].isoformat()
        supabase_admin.table('messages').insert(doc_data).execute()
        
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
    user_resp = supabase_admin.table('users').select('*').eq('id', user_id).execute()
    doc = user_resp.data[0] if user_resp.data else None
    if doc:
        user_data = doc
        
    subs = supabase_admin.table('subscriptions').select('*').eq('user_id', user_id).execute().data or []
    has_active = any(sub.get('status') == 'active' for sub in subs)
    
    computed_status = 'active' if has_active else ('expired' if subs else user_data.get('status', 'pending'))
    
    # Get latest active expiry if any
    expires_at = None
    if subs:
        active_subs = [s for s in subs if s.get('status') == 'active']
        if active_subs:
            def get_ts(s):
                dt = parse_dt(s.get('expires_at'))
                return dt.timestamp() if dt else 0
            latest = max(active_subs, key=get_ts)
            if latest.get('expires_at'):
                expires_at = latest['expires_at']

    reqs = supabase_admin.table('purchase_requests').select('*').eq('user_id', user_id).execute().data or []
    latest_req_status = ""
    if reqs:
        reqs.sort(key=lambda x: parse_dt(x.get('created_at')).timestamp() if x.get('created_at') else 0, reverse=True)
        latest_req_status = reqs[0].get('status', '')

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
        user_doc = supabase_admin.table('users').select('*').eq('id', user_id).execute().data[0]
        ips = user_doc.get('accessed_ips') or []
        devices = user_doc.get('accessed_devices') or []
        
        if client_ip not in ips: 
            ips.append(client_ip)
            if len(ips) > 10: ips = ips[-10:]
            
        parsed_device = parse_device_info(user_agent)
        
        cleaned_devices = []
        for d in devices:
            if '|' in d or d == 'Unknown Device':
                if d not in cleaned_devices: cleaned_devices.append(d)
            else:
                pd = parse_device_info(d)
                if pd not in cleaned_devices: cleaned_devices.append(pd)
                
        if parsed_device not in cleaned_devices:
            cleaned_devices.append(parsed_device)
            
        if len(cleaned_devices) > 10: cleaned_devices = cleaned_devices[-10:]
        devices = cleaned_devices
        supabase_admin.table('users').update({
            'accessed_ips': ips,
            'accessed_devices': devices
        }).eq('id', user_id).execute()
    except Exception as e:
        print(f"Error tracking link access for {user_id}: {e}")
        
    subs = supabase_admin.table('subscriptions').select('*').eq('user_id', user_id).execute().data or []
    
    combined_links = []
    has_active = False
    
    from utils import generate_vless_uri
    import re
    import base64
    from datetime import datetime, timezone
        
    now = datetime.now(timezone.utc)
    
    for sub_doc in subs:
        sub_data = sub_doc
        server_id = sub_data.get('server_id')
        subdomain = None
        status = sub_data.get('status')
        expires_at = sub_data.get('expires_at')
        
        is_expired = False
        if status == 'expired':
            is_expired = True
        elif expires_at:
            expires_at = parse_dt(expires_at)
            if expires_at and expires_at < now:
                is_expired = True
                if status != 'expired':
                    supabase_admin.table('subscriptions').update({'status': 'expired'}).eq('id', sub_doc.get('id')).execute()
                
        if server_id:
            s_resp = supabase_admin.table('servers').select('*').eq('id', server_id).execute()
            server_doc = s_resp.data[0] if s_resp.data else None
            if server_doc:
                server = server_doc
                
                # Reverting back to original_ip because Dynv6 is blocked by ISPs
                if is_expired:
                    active_address = "127.0.0.1"
                else:
                    active_address = server.get('original_ip')
                    has_active = True
                
                vless_uri = None
                server_name = server.get('name', 'BombaVPN Server')
                
                # Prepend country flag emoji if available
                country_code = server.get('country_code', '').upper()
                if country_code and len(country_code) == 2:
                    flag_emoji = chr(ord(country_code[0]) + 127397) + chr(ord(country_code[1]) + 127397)
                    if flag_emoji not in server_name:
                        server_name = f"{flag_emoji} {server_name}"
                        
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
