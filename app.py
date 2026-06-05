from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"
import json
import uuid
import functools
import requests
import threading
import time
from translations import TRANSLATIONS
import urllib.parse
import socket
import ipaddress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from utils import extract_ip_from_json, modify_json_address, extract_name_from_json
from vless_parser import extract_vless_from_text

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)
import secrets
# Security fix: Use a fixed fallback key so user subscription links don't break on server restart
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bomba_vpn_fallback_secret_key_12345')
app.config['SESSION_COOKIE_NAME'] = 'flask_session'

def send_telegram_notification(message):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Telegram notification failed: {e}")

@app.route('/api/admin/stats')
def admin_stats():
    if not getattr(request, 'is_admin', False):
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

# Serializer for secure subscription links
from itsdangerous import URLSafeSerializer
sub_serializer = URLSafeSerializer(app.config['SECRET_KEY'], salt='subscription-link')

# Upload Config
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024 # 20MB limit
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    log_path = os.path.join(app.root_path, 'bomba_error.log')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write("EXCEPTION CAUGHT:\n")
        f.write(traceback.format_exc())
        f.write(str(e) + "\n\n")
    return render_template('500.html'), 500


@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in TRANSLATIONS:
        resp = redirect(request.referrer or '/')
        resp.set_cookie('lang', lang, max_age=60*60*24*365, samesite='Lax')
        return resp
    return redirect('/')

@app.context_processor
def inject_notifications():
    count = 0
    if getattr(request, 'is_admin', False):
        try:
            count = len(list(db.collection('notifications').where('is_read', '==', False).stream()))
        except:
            pass
    return dict(unread_notifications_count=count)

@app.context_processor
def inject_locale():
    lang = request.cookies.get('lang')
    if not lang:
        lang = request.accept_languages.best_match(TRANSLATIONS.keys())
        if not lang:
            lang = 'ar'
    elif lang not in TRANSLATIONS:
        lang = 'ar'
        
    def _(key, *args):
        text = TRANSLATIONS[lang].get(key, key)
        if args:
            text = text.format(*args)
        return text
    return dict(_=_, lang=lang, dir='rtl' if lang == 'ar' else 'ltr')

# Firebase Admin Init
try:
    cred = credentials.Certificate("firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    FIREBASE_READY = True
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")
    FIREBASE_READY = False


# Auth Decorator
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not FIREBASE_READY:
            return "Firebase is not configured correctly on the server. Missing firebase-adminsdk.json", 500
            
        session_cookie = request.cookies.get('session')
        if not session_cookie:
            return redirect(url_for('login'))
            
        try:
            decoded_claims = firebase_auth.verify_session_cookie(session_cookie, check_revoked=False)
            request.user = decoded_claims
            request.is_admin = (decoded_claims.get('email') == 'islamazaizia360@gmail.com')
        except Exception as e:
            # محاولة فك تشفير الجلسة المحلية (للتطوير المحلي)
            is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'
            if not is_production:
                try:
                    from itsdangerous import URLSafeTimedSerializer
                    local_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
                    data = local_serializer.loads(session_cookie, max_age=5*24*3600)  # 5 أيام
                    if data.get('is_local_session'):
                        request.user = {'uid': data['uid'], 'email': data['email'], 'name': data.get('name', '')}
                        request.is_admin = (data.get('email') == 'islamazaizia360@gmail.com')
                        return f(*args, **kwargs)
                except Exception:
                    pass
            print(f"Session verification failed: {e}")
            return redirect(url_for('login'))
            
        return f(*args, **kwargs)
    return decorated_function

thread_started = False
thread_lock = threading.Lock()

@app.before_request
def start_background_thread():
    import datetime
    try:
        with open('debug_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.datetime.now()}] REQUEST HIT: {request.method} {request.url}\n")
    except:
        pass
        
    # CSRF Protection: Validate Origin/Referer for POST requests
    if request.method == 'POST' and request.endpoint not in ['ping', 'debug_check', 'session_login']:
        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        host_url = request.host_url.rstrip('/')
        
        valid = False
        if origin and origin == host_url:
            valid = True
        elif referer and referer.startswith(host_url):
            valid = True
            
        if not valid:
            return "CSRF Token Validation Failed", 403

    global thread_started
    if not thread_started:
        with thread_lock:
            if not thread_started:
                try:
                    checker_thread = threading.Thread(target=background_expiry_checker, daemon=True)
                    checker_thread.start()
                    
                    db.collection('users').on_snapshot(on_users_snapshot)
                    db.collection('servers').on_snapshot(on_servers_snapshot)
                    db.collection('messages').on_snapshot(on_messages_snapshot)
                    db.collection('subscriptions').on_snapshot(on_subscriptions_snapshot)
                    db.collection('pricing_rules').on_snapshot(on_pricing_rules_snapshot)
                    db.collection('source_links').on_snapshot(on_source_links_snapshot)
                    
                    thread_started = True
                except Exception as e:
                    print("Could not start background thread:", e)

@app.after_request
def add_header(response):
    # منع كروم من تخزين الصفحات الديناميكية لتجنب حلقة إعادة التحميل
    if 'Cache-Control' not in response.headers:
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    session_cookie = request.cookies.get('session')
    if session_cookie:
        try:
            decoded = firebase_auth.verify_session_cookie(session_cookie)
            if decoded.get('email') == 'islamazaizia360@gmail.com':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        except:
            pass
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return redirect(url_for('login'))

# نقطة اختبار مؤقتة
@app.route('/debug-check')
def debug_check():
    return f"Server code v2 running OK at {datetime.now()}", 200

@app.route('/api/sessionLogin', methods=['POST'])
@limiter.limit("5 per minute")
def session_login():
    id_token = request.json.get('idToken')
    ref_code = request.json.get('ref_code')
    expires_in = timedelta(days=5)
    is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'
    
    try:
        # Decode token to get user info
        decoded_token = firebase_auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        # Check if user exists, if not, create them with referral data
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()
        if not user_doc.exists:
            user_data = {
                'email': decoded_token.get('email'),
                'status': 'pending',
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                'referral_code': uid[:8],
            }
            if ref_code and ref_code != uid[:8]:
                user_data['referred_by'] = ref_code
            user_ref.set(user_data)
        
        session_cookie = firebase_auth.create_session_cookie(id_token, expires_in=expires_in)
        response = jsonify({'status': 'success'})
        expires = datetime.now() + expires_in
        response.set_cookie('session', session_cookie, expires=expires, httponly=True, secure=is_production, samesite='Lax')
        return response
    except Exception as e:
        with open('debug_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] create_session_cookie FAILED: {type(e).__name__}: {e}\n")
        print(f"Session login error (create_session_cookie): {type(e).__name__}: {e}")
        
        # حل بديل للتطوير المحلي: التحقق من الـ Token مباشرة وإنشاء session cookie يدوياً
        if not is_production:
            try:
                decoded = firebase_auth.verify_id_token(id_token)
                # إنشاء session cookie مخصص باستخدام itsdangerous
                from itsdangerous import URLSafeTimedSerializer
                local_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
                local_session = local_serializer.dumps({
                    'uid': decoded['uid'],
                    'email': decoded.get('email', ''),
                    'name': decoded.get('name', ''),
                    'is_local_session': True
                })
                response = jsonify({'status': 'success'})
                expires = datetime.now() + expires_in
                response.set_cookie('session', local_session, expires=expires, httponly=True, secure=False, samesite='Lax')
                print(f"Local session created for: {decoded.get('email')}")
                return response
            except Exception as e2:
                print(f"Session login error (verify_id_token fallback): {type(e2).__name__}: {e2}")
                return jsonify({'error': str(e2)}), 401
        
        return jsonify({'error': str(e)}), 401
        
@app.route('/api/sessionLogout', methods=['POST'])
def session_logout():
    response = jsonify({'status': 'success'})
    response.set_cookie('session', '', expires=0)
    return response

@app.route('/api/available_servers')
@login_required
def api_available_servers():
    servers = []
    for doc in db.collection('servers').stream():
        s = doc.to_dict()
        s['id'] = doc.id
        # Clean non-serializable fields
        if 'expires_at' in s and s['expires_at']:
            s['expires_at'] = s['expires_at'].isoformat()
        if 'created_at' in s and s['created_at']:
            s['created_at'] = s['created_at'].isoformat()
        servers.append(s)
    return jsonify(servers)

@app.route('/pay', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")
def pay():
    user_id = request.user['uid']
    user_doc = db.collection('users').document(user_id).get()
    
    if user_doc.exists:
        data = user_doc.to_dict()
        
    servers = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for doc in db.collection('servers').stream():
        s = doc.to_dict()
        s_exp = s.get('expires_at')
        if s_exp:
            if s_exp.tzinfo is None:
                s_exp = s_exp.replace(tzinfo=timezone.utc)
            s_exp = s_exp.replace(tzinfo=None)
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
            ext = secure_filename(file.filename).rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
            filename = f"receipt_{user_id}_{uuid.uuid4().hex[:8]}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Save the new purchase request in the dedicated collection
            renew_sub_id = request.form.get('renew_sub_id')
            db.collection('purchase_requests').add({
                'user_id': user_id,
                'email': request.user['email'],
                'server_id': server_id,
                'renew_sub_id': renew_sub_id,
                'receipt_url': filename,
                'status': 'pending',
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
            })
            
            # إرسال إشعار تيليجرام
            msg = f"💳 *دفعة جديدة!*\nالمستخدم: `{request.user['email']}`\nرفع صورة إيصال لاشتراك جديد/تجديد.\nيرجى مراجعة لوحة التحكم."
            send_telegram_notification(msg)
            
            flash('تم إرسال الطلب بنجاح. جاري مراجعته من قبل الإدارة. / Request submitted successfully. Under review.', 'success')
            return redirect(url_for('user_dashboard'))
            
    return render_template('payment.html', servers=servers, user=request.user)

# --- ADMIN ROUTES ---
@app.route('/admin')
@login_required
def admin_dashboard():
    if not request.is_admin:
        return "Unauthorized", 403
        
    servers = []
    for doc in db.collection('servers').stream():
        data = doc.to_dict()
        data['id'] = doc.id
        if 'expires_at' in data and data['expires_at']:
            data['expires_at'] = data['expires_at'].replace(tzinfo=None)
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
            data['created_at'] = data['created_at'].replace(tzinfo=None)
            
        data['subscriptions'] = []
        users_dict[data['id']] = data
        all_users.append(data)
        
    server_map = {s['id']: s.get('name') for s in servers}
    
    # Fetch all subscriptions
    for doc in db.collection('subscriptions').stream():
        sub = doc.to_dict()
        sub['id'] = doc.id
        if 'expires_at' in sub and sub['expires_at']:
            sub['expires_at'] = sub['expires_at'].replace(tzinfo=None)
            
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
            
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Fetch support tickets
    tickets = []
    try:
        for doc in db.collection('messages').order_by('created_at', direction=firestore.Query.DESCENDING).stream():
            msg = doc.to_dict()
            msg['id'] = doc.id
            if 'created_at' in msg and msg['created_at']:
                msg['created_at'] = msg['created_at'].replace(tzinfo=None)
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



@app.route('/admin/notifications')
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
                n['created_at'] = n['created_at'].replace(tzinfo=None)
            notifications.append(n)
    except Exception as e:
        print("Error fetching notifications:", e)
        
    return render_template('notifications.html', notifications=notifications)

@app.route('/admin/notifications/read/<notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    if not request.is_admin:
        return "Unauthorized", 403
    db.collection('notifications').document(notif_id).update({'is_read': True})
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_parent'}), 200
    return redirect(url_for('admin_notifications'))

@app.route('/admin/notifications/read_all', methods=['POST'])
@login_required
def mark_all_read():
    if not request.is_admin:
        return "Unauthorized", 403
    for doc in db.collection('notifications').where('is_read', '==', False).stream():
        db.collection('notifications').document(doc.id).update({'is_read': True})
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_all_notifications', 'message': 'All notifications marked as read'}), 200
    return redirect(url_for('admin_notifications'))

@app.route('/admin/notifications/delete/<notif_id>', methods=['POST'])
@login_required
def delete_notif(notif_id):
    if not request.is_admin:
        return "Unauthorized", 403
    db.collection('notifications').document(notif_id).delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_parent'}), 200
    return redirect(url_for('admin_notifications'))

@app.route('/admin/notifications/delete_all', methods=['POST'])
@login_required
def delete_all_notifs():
    if not request.is_admin:
        return "Unauthorized", 403
    for doc in db.collection('notifications').stream():
        db.collection('notifications').document(doc.id).delete()
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'action': 'remove_all_notifications', 'message': 'All notifications deleted'}), 200
    return redirect(url_for('admin_notifications'))

@app.route('/admin/debts')
@login_required
def admin_debts():
    if not request.is_admin:
        return "Unauthorized", 403
        
    in_debt_users = []
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Pre-fetch servers to avoid many DB calls
        servers_map = {}
        with servers_cache_lock:
            for s_id, s_dict in servers_cache.items():
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
            sub_exp = sub_exp.replace(tzinfo=None)
            
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
            s_exp = s_exp.replace(tzinfo=None)
            
            if s_exp < sub_exp:
                delta = sub_exp - s_exp
                
                u_email = "Unknown"
                with users_cache_lock:
                    if user_id in users_cache:
                        u_email = users_cache[user_id].get('email', 'Unknown')
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
        
    return render_template('debts.html', users=in_debt_users, now=datetime.now(timezone.utc).replace(tzinfo=None))

def get_country_info_bulk(ips):
    import socket
    import requests
    resolved_ips = []
    ip_to_originals = {}
    
    for ip in set(ips):
        if not ip: continue
        try:
            # Simple check if it might be a domain (contains letters, no colons for IPv6)
            if any(c.isalpha() for c in ip) and ':' not in ip:
                try:
                    resolved = socket.gethostbyname(ip)
                except:
                    resolved = ip
            else:
                resolved = ip
                
            resolved_ips.append(resolved)
            if resolved not in ip_to_originals:
                ip_to_originals[resolved] = []
            ip_to_originals[resolved].append(ip)
        except Exception:
            pass
            
    country_map = {}
    resolved_ips = list(set(resolved_ips))
    for i in range(0, len(resolved_ips), 100):
        batch = resolved_ips[i:i+100]
        try:
            resp = requests.post("http://ip-api.com/batch", json=[{"query": r, "fields": "status,country,countryCode,query"} for r in batch], timeout=10)
            if resp.status_code == 200:
                for r in resp.json():
                    if r.get("status") == "success":
                        originals = ip_to_originals.get(r.get("query"), [])
                        for orig in originals:
                            country_map[orig] = (r.get("country"), r.get("countryCode"))
        except Exception as e:
            print("Batch IP error:", e)
            
    return country_map

@app.route('/admin/add_servers', methods=['POST'])
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
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=total_real_seconds)
    
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
                    'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                    'expires_at': expires_at
                })
                added += 1
                
    flash(f'تمت إضافة {added} سيرفرات بنجاح!', 'success')
    return redirect(url_for('admin_dashboard'))

def is_safe_url(target_url):
    """Check if a URL is safe to fetch (prevent SSRF)."""
    try:
        parsed = urllib.parse.urlparse(target_url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
            
        ip_addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_addr)
        
        # Block private, loopback, and reserved IPs
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            return False
        return True
    except Exception:
        return False

def _import_vless_servers(subscription_text, total_plan_seconds, total_real_seconds,
                          plan_days, plan_minutes, price_base, pricing_rules,
                          source_link_id, dedup=False):
    """Parse VLESS configs from `subscription_text` and add new servers to the DB.

    Shared by the manual import flow and the per-link Sync flow. Returns a tuple
    (found, added) where `found` is the number of VLESS configs parsed and `added`
    is the number of brand-new servers created. When `dedup` is True, configs whose
    vless_link already exists are skipped (so re-syncing a link is idempotent).
    """
    parsed_configs = extract_vless_from_text(subscription_text)
    if not parsed_configs:
        return 0, 0

    if total_real_seconds == 0:
        expires_at = None
    else:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=total_real_seconds)

    existing_docs = [s.to_dict() for s in db.collection('servers').stream()]
    existing_servers = [d.get('name', '') for d in existing_docs]
    existing_links = set(d.get('vless_link') for d in existing_docs if d.get('vless_link'))

    config_data_list = []
    ips_to_query = []
    for config_dict in parsed_configs:
        original_link = config_dict.pop('_original_link', '')
        content = json.dumps(config_dict, ensure_ascii=False)
        ip = extract_ip_from_json(content)
        config_data_list.append((config_dict, content, ip, original_link))
        if ip:
            ips_to_query.append(ip)

    country_map = get_country_info_bulk(ips_to_query)

    added = 0
    for config_dict, content, ip, original_link in config_data_list:
        if ip:
            if dedup and original_link and original_link in existing_links:
                continue

            orig_name = extract_name_from_json(content) or "Imported Server"
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

            keywords = []
            if 'gemini' in orig_name_lower: keywords.append("Gemini")
            if 'lte' in orig_name_lower: keywords.append("LTE")
            if 'yt' in orig_name_lower: keywords.append("YT")
            if 'ru' in orig_name_lower: keywords.append("RU")
            if 'torrent' in orig_name_lower: keywords.append("Torrent")

            if keywords:
                final_name = f"{base_name} | {' | '.join(keywords)}"
            else:
                final_name = base_name

            # Determine price based on rules
            final_price = price_base
            keywords_lower = set(k.lower() for k in keywords)

            matched_rules = []
            for rule in pricing_rules:
                if rule['tags'].issubset(keywords_lower) and rule.get('duration_days', 0) == plan_days:
                    matched_rules.append(rule)

            if matched_rules:
                # Prioritize the rule with the most matching tags (highest specificity)
                best_rule = max(matched_rules, key=lambda r: len(r['tags']))
                final_price = best_rule['price']

            existing_servers.append(final_name)
            if original_link:
                existing_links.add(original_link)

            db.collection('servers').add({
                'name': final_name,
                'source_link_id': source_link_id,
                'original_ip': ip,
                'country_code': cc.lower() if cc else None,
                'json_config': content,
                'vless_link': original_link,
                'price': final_price,
                'total_plan_seconds': total_plan_seconds,
                'plan_minutes': plan_minutes,
                'tags': keywords,
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                'expires_at': expires_at
            })
            added += 1

    return len(parsed_configs), added


@app.route('/admin/import_servers', methods=['POST'])
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
    with pricing_rules_cache_lock:
        for r_id, r_dict in pricing_rules_cache.items():
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
                    'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
                })
                source_link_id = doc_ref[1].id

            if not is_safe_url(subscription_text):
                flash('رابط الاستيراد المرفق غير آمن أو يستهدف عناوين محلية محظورة.', 'error')
                return redirect(url_for('admin_dashboard'))

            resp = requests.get(subscription_text, timeout=10, headers={'User-Agent': 'v2rayNG'})
            if resp.status_code == 200:
                subscription_text = resp.text
            else:
                flash(f'فشل جلب الرابط، الكود: {resp.status_code}', 'error')
                return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f'حدث خطأ أثناء جلب الرابط: {e}', 'error')
            return redirect(url_for('admin_dashboard'))
            
    # Parse and add servers (shared with the per-link Sync flow)
    found, added = _import_vless_servers(
        subscription_text, total_plan_seconds, total_real_seconds,
        plan_days, plan_minutes, price_base, pricing_rules, source_link_id
    )

    if found == 0:
        flash('لم يتم العثور على سيرفرات VLESS صالحة في الرابط أو النص.', 'error')
        return redirect(url_for('admin_dashboard'))

    flash(f'تمت إضافة {added} سيرفرات VLESS مستوردة بنجاح!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_server/<server_id>', methods=['POST'])
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
                    update_data['expires_at'] = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=mins)
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

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_server/<server_id>', methods=['POST'])
@login_required
def delete_server(server_id):
    if not request.is_admin: return "Unauthorized", 403
        
    db.collection('servers').document(server_id).delete()
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    
    flash('تم حذف السيرفر وجدولة نقل مستخدميه تلقائياً', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_request/<request_id>', methods=['POST'])
@login_required
def approve_request(request_id):
    if not request.is_admin:
        return "Unauthorized", 403
        
    req_doc_ref = db.collection('purchase_requests').document(request_id)
    req_doc = req_doc_ref.get()
    if not req_doc.exists or req_doc.to_dict().get('status') != 'pending':
        return redirect(url_for('admin_dashboard'))
        
    req_data = req_doc.to_dict()
    user_id = req_data['user_id']
    server_id = req_data['server_id']
    
    user_doc_ref = db.collection('users').document(user_id)
    user_doc = user_doc_ref.get()
    if not user_doc.exists:
        return redirect(url_for('admin_dashboard'))
    user_data = user_doc.to_dict()
        
    days = 30 # default
    hours = 0
    minutes = 0
    s_data = None
        
    server_doc = db.collection('servers').document(server_id).get()
    if server_doc.exists:
        s_data = server_doc.to_dict()
        days = int(s_data.get('plan_days') or 0)
        hours = int(s_data.get('plan_hours') or 0)
        minutes = int(s_data.get('plan_minutes') or 0)
        
        if not days and not hours and not minutes:
            days = 30
        
        email_val = user_data.get('email', '')
        if email_val:
            safe_prefix = email_val.replace('@', '-').replace('.', '-')
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
        'allocated_subdomain': None,
        'status': 'active',
        'required_tags': s_data.get('tags', []) if s_data else [],
        'is_temporary': False,
        'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
        'expires_at': expires_at
    })
    
    # Delete receipt image
    receipt_image = req_data.get('receipt_url')
    if receipt_image:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], receipt_image))
        except OSError: pass
        
    # Mark request as approved
    req_doc_ref.update({'status': 'approved'})
    
    # Update user status if they were new
    if user_data.get('status') != 'active':
        user_doc_ref.update({'status': 'active'})
        
    # Process Referral Reward
    if user_data.get('referred_by'):
        referrer_code = user_data['referred_by']
        referrer_docs = db.collection('users').where('referral_code', '==', referrer_code).limit(1).stream()
        for r_doc in referrer_docs:
            r_user = r_doc.to_dict()
            r_subs = db.collection('subscriptions').where('user_id', '==', r_doc.id).where('status', '==', 'active').stream()
            # Add 7 days to ALL active subs of the referrer, or just the first one
            for r_sub_doc in r_subs:
                r_sub = r_sub_doc.to_dict()
                if 'expires_at' in r_sub and r_sub['expires_at']:
                    new_expiry = r_sub['expires_at'].replace(tzinfo=timezone.utc) + timedelta(days=7)
                    db.collection('subscriptions').document(r_sub_doc.id).update({'expires_at': new_expiry})
                    send_telegram_notification(f"🎉 مكافأة إحالة!\nالمستخدم {user_data.get('email')} اشترى باقة عبر رابط دعوة من {r_user.get('email')}.\nتمت إضافة 7 أيام لاشتراكه بنجاح.")
        # Remove referred_by so it only triggers on first purchase
        user_doc_ref.update({'referred_by': firestore.DELETE_FIELD})
    
    flash('تم الموافقة على الطلب وإنشاء الاشتراك بنجاح / Request approved successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_request/<request_id>', methods=['POST'])
@login_required
def reject_request(request_id):
    if not request.is_admin:
        return "Unauthorized", 403
        
    req_doc_ref = db.collection('purchase_requests').document(request_id)
    req_doc = req_doc_ref.get()
    
    if req_doc.exists:
        req_data = req_doc.to_dict()
        receipt_image = req_data.get('receipt_url')
        if receipt_image:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], receipt_image))
            except OSError: pass
            
        req_doc_ref.update({'status': 'rejected'})
    
    flash('تم رفض الطلب بنجاح / Request rejected successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<user_id>', methods=['POST'])
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
        
    flash('تم حذف المستخدم وجميع بياناته نهائياً / User and all data deleted completely', 'success')
    return redirect(url_for('admin_dashboard'))


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
        'gemini': sum(1 for s in servers_list if 'gemini' in [t.lower() for t in s.get('tags', [])]),
        'yt': sum(1 for s in servers_list if 'yt' in [t.lower() for t in s.get('tags', [])]),
        'lte': sum(1 for s in servers_list if 'lte' in [t.lower() for t in s.get('tags', [])]),
        'ru': sum(1 for s in servers_list if 'ru' in [t.lower() for t in s.get('tags', [])]),
        'torrent': sum(1 for s in servers_list if 'torrent' in [t.lower() for t in s.get('tags', [])])
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
                    
    # Fetch source links, grouping any duplicates (same URL) into a single entry
    source_links_list = []
    try:
        docs_by_url = {}
        for doc in db.collection('source_links').stream():
            d = doc.to_dict()
            d['id'] = doc.id
            if d.get('created_at') and isinstance(d['created_at'], datetime):
                d['created_at'] = d['created_at'].replace(tzinfo=None)
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


@app.route('/api/admin/pricing_rules', methods=['GET', 'POST'])
@login_required
def api_pricing_rules():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    if request.method == 'GET':
        rules = []
        with pricing_rules_cache_lock:
            for r_id, r_dict in pricing_rules_cache.items():
                r = r_dict.copy()
                r['id'] = r_id
                # convert sets or arrays
                if 'tags' in r and isinstance(r['tags'], set):
                    r['tags'] = list(r['tags'])
                rules.append(r)
        return jsonify({'rules': rules})
        
    if request.method == 'POST':
        tags_str = request.form.get('tags', '')
        duration_days = int(request.form.get('duration_days') or 0)
        price = float(request.form.get('price') or 0)
        
        tags_list = [tag.strip().lower() for tag in tags_str.split(',') if tag.strip()]
        
        db.collection('pricing_rules').add({
            'tags': tags_list,
            'duration_days': duration_days,
            'price': price,
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })
        
        # If AJAX, return json. Otherwise redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'success'})
        return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/pricing_rules/<rule_id>/delete', methods=['POST'])
@login_required
def delete_pricing_rule(rule_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    db.collection('pricing_rules').document(rule_id).delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/rescan_servers', methods=['POST'])
@login_required
def rescan_servers():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    # Get all rules
    rules = []
    with pricing_rules_cache_lock:
        for r_id, r_dict in pricing_rules_cache.items():
            r = r_dict.copy()
            # tags might be stored as list in firestore
            r['tags'] = set(r.get('tags', []))
            rules.append(r)
            
    # Iterate all active servers
    updated_count = 0
    with servers_cache_lock:
        server_list = list(servers_cache.items())
        
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
    return redirect(url_for('admin_dashboard'))


@app.route('/api/admin/sync_link/<link_id>', methods=['POST'])
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
    with pricing_rules_cache_lock:
        for r_id, r_dict in pricing_rules_cache.items():
            r = r_dict.copy()
            r['tags'] = set(r.get('tags', []))
            pricing_rules.append(r)

    plan_days = total_plan_seconds // (24 * 3600)

    found, added = _import_vless_servers(
        resp.text, total_plan_seconds, total_real_seconds,
        plan_days, 0, '', pricing_rules, link_id, dedup=True
    )

    return jsonify({'status': 'success', 'found': found, 'added': added})


@app.route('/api/admin/delete_source_link/<link_id>', methods=['POST'])
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


@app.route('/api/admin/pending_requests')
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

@app.route('/admin/manage_subscription/<sub_id>', methods=['POST'])
@login_required
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
                
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage_user_sub/<user_id>', methods=['POST'])
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
                
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/send_message/<user_id>', methods=['POST'])
@login_required
def send_admin_message(user_id):
    if not request.is_admin: return jsonify({"error": "Unauthorized"}), 403
    
    # Support both JSON and Form Data
    message = request.json.get('message') if request.is_json else request.form.get('message')
    
    if not message or not message.strip():
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'status': 'error', 'error': 'Message cannot be empty'}), 400
        flash('Message cannot be empty', 'danger')
        return redirect(url_for('admin_dashboard'))

    dt_now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.collection('admin_messages').add({
        'user_id': user_id,
        'message': message.strip(),
        'created_at': dt_now,
        'is_read': False
    })
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'status': 'success',
            'chat_message': {
                'sender': 'admin',
                'text': message.strip(),
                'timestamp': dt_now.strftime('%Y-%m-%d %H:%M')
            }
        })
        
    flash('تم إرسال الرسالة للمستخدم / Message sent', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/api/chat/<user_id>', methods=['GET'])
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

@app.route('/read_admin_message/<msg_id>', methods=['POST'])
@login_required
def read_admin_message(msg_id):
    user_id = request.user['uid']
    doc = db.collection('admin_messages').document(msg_id).get()
    if doc.exists and doc.to_dict().get('user_id') == user_id:
        db.collection('admin_messages').document(msg_id).update({'is_read': True})
    return jsonify({'success': True})

@app.route('/admin/api/delete_chat/<user_id>', methods=['POST'])
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

@app.route('/admin/support', methods=['GET'])
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
    return render_template('admin_support.html', conversations=sorted_convs, now=datetime.now(timezone.utc).replace(tzinfo=None))

@app.route('/admin/delete_message/<message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    if not request.is_admin:
        return "Unauthorized", 403
    db.collection('messages').document(message_id).delete()
    flash('تم حذف الرسالة بنجاح / Message deleted', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/reply_message/<message_id>', methods=['POST'])
@login_required
def reply_message(message_id):
    if not request.is_admin:
        return "Unauthorized", 403
        
    reply_text = request.form.get('reply')
    if reply_text:
        db.collection('messages').document(message_id).update({
            'admin_reply': reply_text,
            'reply_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })
        flash('تم إرسال الرد بنجاح', 'success')
    return redirect(url_for('admin_dashboard'))

# --- USER ROUTES ---
@app.route('/dashboard')
@login_required
def user_dashboard():
    if request.is_admin:
        return redirect(url_for('admin_dashboard'))
        
    user_id = request.user['uid']
    user_data = None
    
    with users_cache_lock:
        if user_id in users_cache:
            user_data = users_cache[user_id].copy()

    if not user_data:
        try:
            user_doc = db.collection('users').document(user_id).get()
            if not user_doc.exists:
                try:
                    firebase_auth.get_user(user_id)
                    db.collection('users').document(user_id).set({
                        'email': request.user['email'],
                        'status': 'pending',
                        'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                        'referral_code': user_id[:8]
                    })
                    user_data = {'status': 'pending', 'referral_code': user_id[:8]}
                except Exception as e:
                    # User was deleted from Firebase Auth (e.g. by admin)
                    response = make_response(redirect(url_for('login')))
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
        with servers_cache_lock:
            for s_id, s_dict in servers_cache.items():
                server_map[s_id] = s_dict.get('name', 'Unknown')
                
        for doc in db.collection('subscriptions').where('user_id', '==', user_id).stream():
            sub = doc.to_dict()
            sub['id'] = doc.id
            if 'expires_at' in sub and sub['expires_at']:
                if isinstance(sub['expires_at'], datetime):
                    sub['expires_at'] = sub['expires_at'].replace(tzinfo=None)
            
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
        
    user_data['status'] = 'active' if has_active else ('expired' if subscriptions else user_data.get('status', 'pending'))
            
    email = request.user['email']
    # Security fix: Sign the user_id so it cannot be tampered with or guessed
    secure_token = sub_serializer.dumps(user_id)
    sub_link = url_for('get_subscription', token=secure_token, _external=True)
    
    messages = []
    try:
        for doc in db.collection('messages').where('user_id', '==', user_id).stream():
            msg = doc.to_dict()
            msg['id'] = doc.id
            if 'created_at' in msg and msg['created_at']:
                msg['created_at'] = msg['created_at'].replace(tzinfo=None)
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
                msg['created_at'] = msg['created_at'].replace(tzinfo=None)
            else:
                msg['created_at'] = datetime.min
            admin_msgs.append(msg)
        admin_msgs.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
    except Exception as e:
        print("Error fetching admin messages:", e)
        
    return render_template('user_dashboard.html', user_email=email, user=user_data, sub_link=sub_link, messages=messages, admin_msgs=admin_msgs, subscriptions=subscriptions, now=datetime.now(timezone.utc).replace(tzinfo=None))

# --- API ROUTES ---
@app.route('/api/message', methods=['POST'])
@login_required
def send_message():
    text = request.json.get('message') if request.is_json else request.form.get('message')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    
    if text:
        dt_now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.collection('messages').add({
            'user_id': request.user['uid'],
            'email': request.user['email'],
            'message': text,
            'created_at': dt_now,
            'admin_reply': None
        })
        
        # إرسال إشعار تيليجرام
        msg = f"💬 *رسالة دعم جديدة!*\nالمستخدم: `{request.user['email']}`\nالرسالة:\n{text}"
        send_telegram_notification(msg)
        
        if is_ajax:
            return jsonify({
                'status': 'success', 
                'chat_message': {
                    'sender': 'user',
                    'text': text,
                    'timestamp': dt_now.strftime('%Y-%m-%d %H:%M')
                }
            }), 200
        flash('تم إرسال رسالتك بنجاح', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/api/user_status')
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
                expires_at = latest['expires_at'].replace(tzinfo=None).isoformat()

    return jsonify({
        'status': computed_status,
        'has_pending_renewal': user_data.get('has_pending_renewal', False),
        'expires_at': expires_at or ""
    })

@app.route('/sub/<token>')
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


import threading

users_cache = {}
users_cache_lock = threading.Lock()

def on_users_snapshot(col_snapshot, changes, read_time):
    with users_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                doc_dict = change.document.to_dict()
                if doc_dict.get('status') == 'active':
                    users_cache[change.document.id] = doc_dict
                else:
                    users_cache.pop(change.document.id, None)
            elif change.type.name == 'REMOVED':
                users_cache.pop(change.document.id, None)

servers_cache = {}
servers_cache_lock = threading.Lock()

def on_servers_snapshot(col_snapshot, changes, read_time):
    with servers_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                servers_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                servers_cache.pop(change.document.id, None)

messages_cache = {}
messages_cache_lock = threading.Lock()

def on_messages_snapshot(col_snapshot, changes, read_time):
    with messages_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                messages_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                messages_cache.pop(change.document.id, None)



source_links_cache = {}
source_links_cache_lock = threading.Lock()

def on_source_links_snapshot(col_snapshot, changes, read_time):
    with source_links_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                source_links_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                source_links_cache.pop(change.document.id, None)

pricing_rules_cache = {}
pricing_rules_cache_lock = threading.Lock()

def on_pricing_rules_snapshot(col_snapshot, changes, read_time):
    with pricing_rules_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                pricing_rules_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                pricing_rules_cache.pop(change.document.id, None)

subscriptions_cache = {}
subscriptions_cache_lock = threading.Lock()

def on_subscriptions_snapshot(col_snapshot, changes, read_time):
    with subscriptions_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                subscriptions_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                subscriptions_cache.pop(change.document.id, None)

def background_expiry_checker():
    print("Starting Auto-Migration background worker...")
    time.sleep(10)
    
    while True:
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
            with servers_cache_lock:
                all_active_servers = []
                for s_id, s_dict in servers_cache.items():
                    s = s_dict.copy()
                    s['id'] = s_id
                    s_expires = s.get('expires_at')
                    if s_expires and s_expires.replace(tzinfo=None) > now:
                        all_active_servers.append(s)

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
                    
                    if server_dead or is_temp:
                        required_tags = set(sub.get('required_tags') or [])
                        candidate_servers = []
                        for s in all_active_servers:
                            s_tags = set(s.get('tags') or [])
                            if required_tags.issubset(s_tags):
                                candidate_servers.append(s)
                                
                        if candidate_servers:
                            best_server = max(candidate_servers, key=lambda s: s['expires_at'].replace(tzinfo=None))
                            new_temp = False
                        elif server_dead:
                            if not all_active_servers:
                                continue
                            best_server = max(all_active_servers, key=lambda s: s['expires_at'].replace(tzinfo=None))
                            new_temp = True
                        else:
                            continue
                            
                        if best_server['id'] != allocated_server_id:
                            user_doc = db.collection('users').document(sub.get('user_id')).get()
                            if user_doc.exists:
                                user_data = user_doc.to_dict()
                                safe_prefix = user_data.get('email', '').replace('@', '-').replace('.', '-')
                                
                                
                                
                                db.collection('subscriptions').document(sub_id).update({
                                    'server_id': best_server['id'],
                                    'allocated_subdomain': None,
                                    'is_temporary': new_temp
                                })
                                
                                best_exp = best_server['expires_at'].replace(tzinfo=None)
                                exp_at_naive = expires_at.replace(tzinfo=None) if expires_at else now
                                if best_exp < exp_at_naive:
                                    debt_delta = exp_at_naive - best_exp
                                    db.collection('notifications').add({
                                        'title': 'نقل تلقائي مع دين',
                                        'message': f'تم نقل الاشتراك {sub_id} للمستخدم {user_data.get("email")} إلى سيرفر جديد سينتهي قبل اشتراكه! هناك دين بقيمة {debt_delta.days} يوم.',
                                        'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                                        'is_read': False,
                                        'type': 'debt'
                                    })
                except Exception as e:
                    print(f"Error processing sub {sub_id} in background task: {e}")
                    continue
        except Exception as e:
            print(f"Background expiry checker error: {e}")
            
        time.sleep(60)

@app.route('/ping')
def ping():
    return "OK", 200

def keep_alive():
    """
    Pings the server every 10 minutes to prevent Render's free tier from sleeping.
    """
    while True:
        time.sleep(10 * 60)  # Sleep 10 minutes
        try:
            target_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://127.0.0.1:10000')
            if not target_url.endswith('/'): target_url += '/'
            requests.get(f'{target_url}ping', timeout=10)
            print(f"Self-ping successful: Kept server awake ({target_url}).")
        except Exception as e:
            print(f"Self-ping failed: {e}")

@app.route('/migrate-db-once')
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
                    'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
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
                    'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
                }
                db.collection('purchase_requests').add(req_data)
                reqs_count += 1
                
    return f"Migrated {subs_count} active subscriptions and {reqs_count} pending requests."

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

@app.route('/api/cron/daily', methods=['GET', 'POST'])
def cron_daily():
    # This endpoint should be triggered by cron-job.org once a day
    smtp_email = os.environ.get('SMTP_EMAIL')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    
    if not smtp_email or not smtp_password:
        return jsonify({'status': 'error', 'message': 'SMTP not configured'}), 400
        
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
                expires_at = expires_at.replace(tzinfo=None)
                
            # If expiring within 48 hours but strictly in the future
            if now < expires_at <= reminder_threshold:
                # Check if reminder already sent recently
                last_sent = sub.get('reminder_sent_at')
                if last_sent:
                    if hasattr(last_sent, 'tzinfo') and last_sent.tzinfo is not None:
                        last_sent = last_sent.replace(tzinfo=None)
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

if __name__ == '__main__':
    # Start the Keep-Alive thread
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    
    # فتح المتصفح تلقائياً على الرابط الصحيح إذا كنا نعمل محلياً
    if not os.environ.get('RENDER') and not os.environ.get('WERKZEUG_RUN_MAIN'):
        import webbrowser
        from threading import Timer
        Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
