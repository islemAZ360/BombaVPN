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

from utils import extract_ip_from_json, modify_json_address, extract_name_from_json
from vless_parser import extract_vless_from_text
from dns_manager import create_dns_record, delete_dns_record

app = Flask(__name__)
import secrets
# Security fix: Use a strong random key by default if env variable is missing
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_NAME'] = 'flask_session'

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
def internal_server_error(e):
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
    lang = request.cookies.get('lang', 'ar')
    if lang not in TRANSLATIONS:
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

# Configuration for Dynv6
DYNV6_TOKEN = os.environ.get('DYNV6_TOKEN', 'YOUR_DYNV6_TOKEN_HERE')
BASE_ZONE = os.environ.get('BASE_ZONE', 'bombavpn.dynv6.net')

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
            print(f"Session verification failed: {e}")
            return redirect(url_for('login'))
            
        return f(*args, **kwargs)
    return decorated_function

thread_started = False
thread_lock = threading.Lock()

@app.before_request
def start_background_thread():
    global thread_started
    if not thread_started:
        with thread_lock:
            if not thread_started:
                try:
                    checker_thread = threading.Thread(target=background_expiry_checker, daemon=True)
                    checker_thread.start()
                    thread_started = True
                except Exception as e:
                    print("Could not start background thread:", e)

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
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return redirect(url_for('login'))

@app.route('/api/sessionLogin', methods=['POST'])
def session_login():
    id_token = request.json.get('idToken')
    expires_in = timedelta(days=5)
    try:
        session_cookie = firebase_auth.create_session_cookie(id_token, expires_in=expires_in)
        response = jsonify({'status': 'success'})
        expires = datetime.now() + expires_in
        # Security fix: Set secure=True if running in production (Render sets RENDER env var)
        is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'
        response.set_cookie('session', session_cookie, expires=expires, httponly=True, secure=is_production, samesite='Lax')
        return response
    except Exception as e:
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
def pay():
    user_id = request.user['uid']
    user_doc = db.collection('users').document(user_id).get()
    
    if user_doc.exists:
        data = user_doc.to_dict()
        if data.get('status') == 'review' or data.get('has_pending_renewal'):
            return redirect(url_for('user_dashboard'))
        
    servers = []
    for doc in db.collection('servers').stream():
        s = doc.to_dict()
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
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"receipt_{user_id}_{uuid.uuid4().hex[:8]}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            if user_doc.exists and user_doc.to_dict().get('status') == 'active':
                old_receipt = user_doc.to_dict().get('renewal_receipt_image')
                if old_receipt:
                    try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_receipt))
                    except OSError: pass

                db.collection('users').document(user_id).update({
                    'has_pending_renewal': True,
                    'renewal_receipt_image': filename,
                    'renewal_requested_server_id': server_id,
                    'renewal_created_at': datetime.utcnow()
                })
            else:
                if user_doc.exists:
                    old_receipt = user_doc.to_dict().get('receipt_image')
                    if old_receipt:
                        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_receipt))
                        except OSError: pass
                
                db.collection('users').document(user_id).set({
                    'email': request.user['email'],
                    'status': 'review',
                    'receipt_image': filename,
                    'requested_server_id': server_id,
                    'created_at': datetime.utcnow()
                }, merge=True)
            
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
    
    for doc in db.collection('users').stream():
        data = doc.to_dict()
        data['id'] = doc.id
        if 'created_at' in data and data['created_at']:
            data['created_at'] = data['created_at'].replace(tzinfo=None)
        if 'subscription_expires_at' in data and data['subscription_expires_at']:
            data['subscription_expires_at'] = data['subscription_expires_at'].replace(tzinfo=None)
            
        all_users.append(data)
        
        if data.get('status') == 'active':
            active_users.append(data)
            
    # Add server name to all_users for easy display
    server_map = {s['id']: s.get('name') for s in servers}
    for u in all_users:
        if u.get('allocated_server_id'):
            u['allocated_server_name'] = server_map.get(u['allocated_server_id'], 'Unknown')
            
    # 1. New users
    for doc in db.collection('users').where('status', 'in', ['pending', 'review']).stream():
        u = doc.to_dict()
        if u.get('status') == 'review':
            u['id'] = doc.id
            u['is_renewal'] = False
            pending_users.append(u)
            
    # 2. Renewing users
    for doc in db.collection('users').where('has_pending_renewal', '==', True).stream():
        u = doc.to_dict()
        u['id'] = doc.id
        u['is_renewal'] = True
        u['receipt_image'] = u.get('renewal_receipt_image') # Alias for template
        u['requested_server_id'] = u.get('renewal_requested_server_id')
        pending_users.append(u)
        
    for u in pending_users:
        s_id = u.get('requested_server_id')
        if s_id:
            s_doc = db.collection('servers').document(s_id).get()
            if s_doc.exists:
                u['server'] = s_doc.to_dict()
            
    now = datetime.utcnow()
    
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
        'gemini': sum(1 for s in servers if 'Gemini' in s.get('tags', [])),
        'yt': sum(1 for s in servers if 'YT' in s.get('tags', [])),
        'lte': sum(1 for s in servers if 'LTE' in s.get('tags', []))
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

@app.route('/admin/debts')
@login_required
def admin_debts():
    if not request.is_admin:
        return "Unauthorized", 403
        
    in_debt_users = []
    try:
        # We fetch users marked as in debt
        for doc in db.collection('users').where('is_in_debt', '==', True).stream():
            u = doc.to_dict()
            u['id'] = doc.id
            if 'subscription_expires_at' in u and u['subscription_expires_at']:
                u['subscription_expires_at'] = u['subscription_expires_at'].replace(tzinfo=None)
            
            # Fetch allocated server to calculate exact debt
            alloc_id = u.get('allocated_server_id')
            if alloc_id:
                s_doc = db.collection('servers').document(alloc_id).get()
                if s_doc.exists:
                    s_data = s_doc.to_dict()
                    s_exp = s_data.get('expires_at')
                    if s_exp:
                        s_exp = s_exp.replace(tzinfo=None)
                        u['server_name'] = s_data.get('name')
                        u['server_expires_at'] = s_exp
                        if u['subscription_expires_at'] and s_exp < u['subscription_expires_at']:
                            delta = u['subscription_expires_at'] - s_exp
                            u['debt_days'] = delta.days
                            u['debt_hours'] = delta.seconds // 3600
                        else:
                            u['debt_days'] = 0
                            u['debt_hours'] = 0
                else:
                    u['server_name'] = None
                    u['debt_days'] = None
                    u['debt_hours'] = None
            
            in_debt_users.append(u)
    except Exception as e:
        print("Error fetching debts:", e)
        
    return render_template('debts.html', users=in_debt_users, now=datetime.utcnow())

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
    plan_days = int(request.form.get('plan_days') or 0)
    plan_hours = int(request.form.get('plan_hours') or 0)
    plan_minutes = int(request.form.get('plan_minutes') or 0)
    
    real_days = int(request.form.get('real_days') or 0)
    real_hours = int(request.form.get('real_hours') or 0)
    real_minutes = int(request.form.get('real_minutes') or 0)
    
    price = request.form.get('price') or ''
    
    expires_at = datetime.utcnow() + timedelta(days=real_days, hours=real_hours, minutes=real_minutes)
    
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
                    'created_at': datetime.utcnow(),
                    'expires_at': expires_at
                })
                added += 1
                
    flash(f'تمت إضافة {added} سيرفرات بنجاح!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/import_servers', methods=['POST'])
@login_required
def import_servers():
    if not request.is_admin:
        return "Unauthorized", 403
        
    subscription_text = request.form.get('subscription_text', '').strip()
    plan_days = int(request.form.get('plan_days') or 0)
    plan_hours = int(request.form.get('plan_hours') or 0)
    plan_minutes = int(request.form.get('plan_minutes') or 0)
    
    real_days = int(request.form.get('real_days') or 0)
    real_hours = int(request.form.get('real_hours') or 0)
    real_minutes = int(request.form.get('real_minutes') or 0)
    
    price_base = request.form.get('price_base') or ''
    rule_tags = request.form.getlist('rule_tags[]')
    rule_prices = request.form.getlist('rule_prices[]')
    
    pricing_rules = []
    for t_str, p_str in zip(rule_tags, rule_prices):
        if t_str and p_str:
            tags_set = set(tag.strip().lower() for tag in t_str.split(',') if tag.strip())
            if tags_set:
                pricing_rules.append({'tags': tags_set, 'price': p_str.strip()})
    
    expires_at = datetime.utcnow() + timedelta(days=real_days, hours=real_hours, minutes=real_minutes)
    
    # Strip happ://add/ if present
    if subscription_text.startswith('happ://add/'):
        subscription_text = subscription_text.replace('happ://add/', '')
    
    # If the text is a URL, fetch it
    if subscription_text.startswith('http://') or subscription_text.startswith('https://'):
        try:
            resp = requests.get(subscription_text, timeout=10, headers={'User-Agent': 'v2rayNG'})
            if resp.status_code == 200:
                subscription_text = resp.text
            else:
                flash(f'فشل جلب الرابط، الكود: {resp.status_code}', 'error')
                return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f'حدث خطأ أثناء جلب الرابط: {e}', 'error')
            return redirect(url_for('admin_dashboard'))
            
    # Parse the VLESS links
    parsed_configs = extract_vless_from_text(subscription_text)
    
    if not parsed_configs:
        flash('لم يتم العثور على سيرفرات VLESS صالحة في الرابط أو النص.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    added = 0
    existing_servers = [s.to_dict().get('name', '') for s in db.collection('servers').stream()]
    
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
    
    for config_dict, content, ip, original_link in config_data_list:
        if ip:
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
            
            if keywords:
                final_name = f"{base_name} | {' | '.join(keywords)}"
            else:
                final_name = base_name
                
            # Determine price based on rules
            final_price = price_base
            keywords_lower = set(k.lower() for k in keywords)
            
            matched_rules = []
            for rule in pricing_rules:
                if rule['tags'].issubset(keywords_lower):
                    matched_rules.append(rule)
                    
            if matched_rules:
                # Prioritize the rule with the most matching tags (highest specificity)
                best_rule = max(matched_rules, key=lambda r: len(r['tags']))
                final_price = best_rule['price']

            existing_servers.append(final_name)
            
            db.collection('servers').add({
                'name': final_name,
                'original_ip': ip,
                'country_code': cc.lower() if cc else None,
                'json_config': content,
                'vless_link': original_link,
                'price': final_price,
                'plan_days': plan_days,
                'plan_hours': plan_hours,
                'plan_minutes': plan_minutes,
                'tags': keywords,
                'created_at': datetime.utcnow(),
                'expires_at': expires_at
            })
            added += 1
            
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
    
    # Flag users for auto-recovery
    users_on_server = db.collection('users').where('allocated_server_id', '==', server_id).stream()
    for udoc in users_on_server:
        db.collection('users').document(udoc.id).update({
            'is_in_debt': True
        })
        
    db.collection('servers').document(server_id).delete()
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    
    flash('تم حذف السيرفر وجدولة نقل مستخدميه تلقائياً', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_user/<user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    if not request.is_admin:
        return "Unauthorized", 403
        
    user_doc = db.collection('users').document(user_id).get()
    if not user_doc.exists:
        return redirect(url_for('admin_dashboard'))
        
    user_data = user_doc.to_dict()
    is_renewal = user_data.get('has_pending_renewal', False)
    server_id = user_data.get('renewal_requested_server_id') if is_renewal else user_data.get('requested_server_id')
    days = 30 # default
    hours = 0
    minutes = 0
    s_data = None
    
    subdomain = None
    if server_id:
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
                subdomain = f"{safe_prefix}.{BASE_ZONE}"
                
                # Check if this exact subdomain/IP is already allocated
                old_subdomain = user_data.get('allocated_subdomain')
                if old_subdomain != subdomain or user_data.get('allocated_server_id') != server_id:
                    if old_subdomain:
                        delete_dns_record(old_subdomain, DYNV6_TOKEN)
                    create_dns_record(subdomain, s_data['original_ip'], DYNV6_TOKEN)
                
    duration_delta = timedelta(days=days, hours=hours, minutes=minutes)
    
    current_expires_at = user_data.get('subscription_expires_at')
    if current_expires_at:
        current_expires_at = current_expires_at.replace(tzinfo=None)
        
    if is_renewal and current_expires_at and current_expires_at > datetime.utcnow():
        # Add to existing time
        expires_at = current_expires_at + duration_delta
    else:
        expires_at = datetime.utcnow() + duration_delta
    
    current_count = user_data.get('purchases_count', 0)
    update_data = {
        'subscription_expires_at': expires_at,
        'allocated_server_id': server_id,
        'status': 'active',
        'is_in_debt': False,
        'purchases_count': current_count + 1
    }
    
    if is_renewal:
        update_data['has_pending_renewal'] = False
        update_data['renewal_receipt_image'] = None
        update_data['renewal_requested_server_id'] = None
        receipt_image = user_data.get('renewal_receipt_image')
        if receipt_image:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], receipt_image))
            except OSError: pass
    else:
        update_data['receipt_image'] = None
        update_data['requested_server_id'] = None
        receipt_image = user_data.get('receipt_image')
        if receipt_image:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], receipt_image))
            except OSError: pass
        
    if server_id and s_data:
        update_data['required_tags'] = s_data.get('tags', [])
        s_expires = s_data.get('expires_at')
        if s_expires:
            s_expires = s_expires.replace(tzinfo=None)
            if s_expires < expires_at:
                update_data['is_in_debt'] = True
                debt_delta = expires_at - s_expires
                db.collection('notifications').add({
                    'title': 'تنبيه ديون جديدة',
                    'message': f'المستخدم {user_data.get("email")} يتطلب وقتاً أطول من السيرفر المخصص! لديك دين له بقيمة {debt_delta.days} يوم و {debt_delta.seconds // 3600} ساعة.',
                    'created_at': datetime.utcnow(),
                    'is_read': False,
                    'type': 'debt'
                })
    
    if subdomain:
        update_data['allocated_subdomain'] = subdomain
        
    db.collection('users').document(user_id).update(update_data)
    
    flash('تم تفعيل الحساب بنجاح / Account activated successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_user/<user_id>', methods=['POST'])
@login_required
def reject_user(user_id):
    if not request.is_admin:
        return "Unauthorized", 403
        
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        is_renewal = user_data.get('has_pending_renewal', False)
        
        if is_renewal:
            receipt_image = user_data.get('renewal_receipt_image')
            if receipt_image:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], receipt_image))
                except OSError: pass
            
            db.collection('users').document(user_id).update({
                'has_pending_renewal': False,
                'renewal_receipt_image': None,
                'renewal_requested_server_id': None
            })
        else:
            receipt_image = user_data.get('receipt_image')
            if receipt_image:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], receipt_image))
                except OSError: pass
                
            db.collection('users').document(user_id).update({
                'status': 'pending',
                'receipt_image': None,
                'requested_server_id': None
            })
    
    flash('تم رفض الإيصال', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not request.is_admin: return "Unauthorized", 403
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        data = user_doc.to_dict()
        sub = data.get('allocated_subdomain')
        if sub: delete_dns_record(sub, DYNV6_TOKEN)
    db.collection('users').document(user_id).delete()
    
    # Delete from Firebase Auth as well
    try:
        firebase_auth.delete_user(user_id)
    except Exception as e:
        print(f"Error deleting user from Firebase Auth: {e}")
        
    flash('تم حذف المستخدم نهائياً / User deleted completely', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/pending_requests')
@login_required
def api_pending_requests():
    if not getattr(request, 'is_admin', False):
        return "Unauthorized", 403
        
    users_ref = db.collection('users')
    query = users_ref.where('status', 'in', ['pending', 'review']).stream()
    
    pending_users = []
    for doc in query:
        u = doc.to_dict()
        u['id'] = doc.id
        # Convert datetime objects to string for JSON serialization
        for k, v in u.items():
            if isinstance(v, datetime):
                u[k] = v.isoformat()
        
        # Get server details if applicable
        if u.get('allocated_server_id'):
            s_doc = db.collection('servers').document(u['allocated_server_id']).get()
            if s_doc.exists:
                u['server'] = s_doc.to_dict()
                u['server']['id'] = s_doc.id
        
        pending_users.append(u)
        
    return jsonify(pending_users)

@app.route('/admin/manage_user_sub/<user_id>', methods=['POST'])
@login_required
def manage_user_sub(user_id):
    if not request.is_admin: return "Unauthorized", 403
    action = request.form.get('action')
    
    user_doc = db.collection('users').document(user_id).get()
    if not user_doc.exists: return redirect(url_for('admin_dashboard'))
    data = user_doc.to_dict()
    
    if action == 'cancel':
        update_data = {'status': 'expired'}
        if data.get('allocated_subdomain'):
            delete_dns_record(data['allocated_subdomain'], DYNV6_TOKEN)
            update_data['allocated_subdomain'] = None
            update_data['allocated_server_id'] = None
        db.collection('users').document(user_id).update(update_data)
        flash('تم إلغاء الاشتراك بنجاح / Subscription cancelled', 'success')
        
    elif action == 'modify':
        modify_type = request.form.get('modify_type', 'add')
        days = int(request.form.get('days') or 0)
        hours = int(request.form.get('hours') or 0)
        minutes = int(request.form.get('minutes') or 0)
        seconds = int(request.form.get('seconds') or 0)
        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        
        current_expires = data.get('subscription_expires_at')
        if current_expires:
            current_expires = current_expires.replace(tzinfo=None)
        else:
            current_expires = datetime.utcnow()
            
        if modify_type == 'add':
            new_expires = current_expires + delta
        elif modify_type == 'subtract':
            new_expires = current_expires - delta
        else: # set
            new_expires = datetime.utcnow() + delta
            
        new_expires_aware = new_expires.replace(tzinfo=timezone.utc)
            
        db.collection('users').document(user_id).update({
            'subscription_expires_at': new_expires_aware,
            'status': 'active' if new_expires > datetime.utcnow() else 'expired'
        })
        flash('تم تعديل المدة بنجاح / Duration modified', 'success')
        
    elif action == 'assign':
        server_id = request.form.get('server_id')
        if server_id:
            s_doc = db.collection('servers').document(server_id).get()
            if s_doc.exists:
                s_data = s_doc.to_dict()
                email_val = data.get('email', '')
                subdomain = f"{email_val.replace('@', '-').replace('.', '-')}.{BASE_ZONE}"
                
                old_subdomain = data.get('allocated_subdomain')
                if old_subdomain != subdomain or data.get('allocated_server_id') != server_id:
                    if old_subdomain: delete_dns_record(old_subdomain, DYNV6_TOKEN)
                    create_dns_record(subdomain, s_data['original_ip'], DYNV6_TOKEN)
                
                db.collection('users').document(user_id).update({
                    'allocated_server_id': server_id,
                    'allocated_subdomain': subdomain,
                    'status': 'active'
                })
                flash('تم تعيين السيرفر بنجاح / Server assigned', 'success')
                
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/send_message/<user_id>', methods=['POST'])
@login_required
def send_admin_message(user_id):
    if not request.is_admin: return "Unauthorized", 403
    message = request.form.get('message')
    if message:
        db.collection('admin_messages').add({
            'user_id': user_id,
            'message': message,
            'created_at': datetime.utcnow(),
            'is_read': False
        })
        flash('تم إرسال الرسالة للمستخدم / Message sent', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/read_admin_message/<msg_id>', methods=['POST'])
@login_required
def read_admin_message(msg_id):
    user_id = request.user['uid']
    doc = db.collection('admin_messages').document(msg_id).get()
    if doc.exists and doc.to_dict().get('user_id') == user_id:
        db.collection('admin_messages').document(msg_id).update({'is_read': True})
    return jsonify({'success': True})

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
            'reply_at': datetime.utcnow()
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
                db.collection('users').document(user_id).set({
                    'email': request.user['email'],
                    'status': 'pending',
                    'created_at': datetime.utcnow()
                })
                user_data = {'status': 'pending'}
            else:
                user_data = user_doc.to_dict()
        except Exception as e:
            print(f"Error fetching user doc in dashboard: {e}")
            user_data = {'status': 'pending', 'error': 'db_quota'}

    if 'subscription_expires_at' in user_data and user_data['subscription_expires_at']:
        if isinstance(user_data['subscription_expires_at'], datetime):
            user_data['subscription_expires_at'] = user_data['subscription_expires_at'].replace(tzinfo=None)
            
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
        
    server = None
    if user_data.get('status') == 'active' and user_data.get('allocated_server_id'):
        allocated_server_id = user_data.get('allocated_server_id')
        with servers_cache_lock:
            if allocated_server_id in servers_cache:
                server = servers_cache[allocated_server_id].copy()
                
        if not server:
            try:
                s_doc = db.collection('servers').document(allocated_server_id).get()
                if s_doc.exists:
                    server = s_doc.to_dict()
            except Exception as e:
                print("Error fetching server in dashboard:", e)
            
    if user_data.get('status') == 'active' and server is None:
        # Trigger reassignment
        try:
            get_subscription(user_id)
            with users_cache_lock:
                if user_id in users_cache:
                    user_data = users_cache[user_id].copy()
            if user_data.get('status') == 'active' and user_data.get('allocated_server_id'):
                with servers_cache_lock:
                    if user_data.get('allocated_server_id') in servers_cache:
                        server = servers_cache[user_data.get('allocated_server_id')].copy()
        except Exception as e:
            print("Error in reassignment dashboard:", e)
    
    if 'subscription_expires_at' in user_data and user_data['subscription_expires_at'] and not isinstance(user_data['subscription_expires_at'], datetime):
        pass
    if 'subscription_expires_at' in user_data and isinstance(user_data['subscription_expires_at'], datetime):
        user_data['subscription_expires_at'] = user_data['subscription_expires_at'].replace(tzinfo=None)
        
    if server:
        try:
            if 'json_config' in server:
                conf = json.loads(server['json_config'])
                for ob in conf.get('outbounds', []):
                    if ob.get('protocol') in ['vless', 'vmess', 'trojan']:
                        vnext = ob.get('settings', {}).get('vnext', [])
                        if vnext:
                            server['ip'] = server.get('ip') or vnext[0].get('address', '')
                            server['port'] = server.get('port') or vnext[0].get('port', 443)
                            users = vnext[0].get('users', [])
                            if users:
                                server['uuid'] = server.get('uuid') or users[0].get('id', '')
                        break
        except Exception as e:
            print("Error parsing server config for dashboard:", e)
            
    return render_template('user_dashboard.html', user_email=email, user=user_data, sub_link=sub_link, messages=messages, admin_msgs=admin_msgs, server=server, now=datetime.utcnow())

# --- API ROUTES ---
@app.route('/api/message', methods=['POST'])
@login_required
def send_message():
    text = request.form.get('message')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if text:
        db.collection('messages').add({
            'user_id': request.user['uid'],
            'email': request.user['email'],
            'message': text,
            'created_at': datetime.utcnow(),
            'admin_reply': None
        })
        if is_ajax:
            return jsonify({'status': 'success', 'message': TRANSLATIONS.get(request.cookies.get('lang', 'ar'), {}).get('Message sent successfully', 'Message sent successfully'), 'action': 'clear'}), 200
        flash('تم إرسال رسالتك بنجاح', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/api/user_status')
@login_required
def api_user_status():
    user_id = request.user['uid']
    doc = db.collection('users').document(user_id).get()
    if doc.exists:
        data = doc.to_dict()
        expires_at = data.get('subscription_expires_at')
        if expires_at:
            expires_at = expires_at.replace(tzinfo=None).isoformat()
        return jsonify({
            'status': data.get('status'),
            'has_pending_renewal': data.get('has_pending_renewal', False),
            'expires_at': expires_at
        })
    return jsonify({'status': 'unknown', 'has_pending_renewal': False, 'expires_at': None}), 404

@app.route('/sub/<token>')
def get_subscription(token):
    # Security fix: Verify the signed token
    try:
        user_id = sub_serializer.loads(token)
    except Exception:
        return "Invalid subscription token.", 403
        
    subs_ref = db.collection('subscriptions').where('user_id', '==', user_id).stream()
    subs = list(subs_ref)
    
    combined_links = []
    has_active = False
    
    from utils import generate_vless_uri
    import re
    import base64
    from datetime import datetime, timezone
    from dns_manager import delete_dns_record
    
    now = datetime.now(timezone.utc)
    
    for sub_doc in subs:
        sub_data = sub_doc.to_dict()
        server_id = sub_data.get('server_id')
        subdomain = sub_data.get('allocated_subdomain')
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
                    if subdomain:
                        delete_dns_record(subdomain, DYNV6_TOKEN)
                
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
                if server.get('vless_link'):
                    vless_uri = re.sub(r'(@)([^:?#]+)', r'\g<1>' + active_address, server['vless_link'], count=1)
                elif server.get('json_config'):
                    vless_uri = generate_vless_uri(server['json_config'], active_address)
                    
                if vless_uri:
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

def background_expiry_checker():
    print("Starting Firestore realtime listeners for background task...")
    users_watch = None
    servers_watch = None
    
    while True:
        try:
            if not users_watch:
                users_watch = db.collection('users').on_snapshot(on_users_snapshot)
            if not servers_watch:
                servers_watch = db.collection('servers').on_snapshot(on_servers_snapshot)
            
            # If both succeeded, break out of initialization loop
            if users_watch and servers_watch:
                print("Firestore listeners started successfully!")
                break
        except Exception as e:
            print(f"Error starting Firestore listeners (Quota exceeded? Retrying in 5m): {e}")
            time.sleep(300) # Wait 5 minutes before retrying

    while True:
        try:
            now = datetime.utcnow()
            
            with servers_cache_lock:
                all_active_servers = []
                for s_id, s_dict in servers_cache.items():
                    s = s_dict.copy()
                    s['id'] = s_id
                    s_expires = s.get('expires_at')
                    if s_expires and s_expires.replace(tzinfo=None) > now:
                        all_active_servers.append(s)

            with users_cache_lock:
                current_users = {uid: u.copy() for uid, u in users_cache.items()}

            for user_id, user in current_users.items():
                try:
                    expires_at = user.get('subscription_expires_at')
                    if expires_at:
                        expires_at = expires_at.replace(tzinfo=None)
                        if now > expires_at:
                            print(f"Background check: User {user.get('email')} expired. Revoking access.")
                            update_data = {'status': 'expired'}
                            if user.get('allocated_subdomain'):
                                delete_dns_record(user.get('allocated_subdomain'), DYNV6_TOKEN)
                                update_data['allocated_subdomain'] = None
                                update_data['allocated_server_id'] = None
                            
                            db.collection('users').document(user_id).update(update_data)
                            continue
                            
                    # Auto-recovery for temporary servers or debts
                    if user.get('is_temporary_server') or user.get('is_in_debt'):
                        required_tags = set(user.get('required_tags') or [])
                        candidate_servers = []
                        for s in all_active_servers:
                            s_tags = set(s.get('tags') or [])
                            if required_tags.issubset(s_tags):
                                candidate_servers.append(s)
                                
                        if candidate_servers:
                            user_expiry = expires_at if expires_at else now
                            valid_servers = [s for s in candidate_servers if s['expires_at'].replace(tzinfo=None) >= user_expiry]
                            
                            if valid_servers:
                                best_server = min(valid_servers, key=lambda s: s['expires_at'].replace(tzinfo=None))
                                new_in_debt = False
                                new_temp = False
                            else:
                                best_server = max(candidate_servers, key=lambda s: s['expires_at'].replace(tzinfo=None))
                                new_in_debt = True
                                # If they required tags but we found matching tags, it's no longer temporary (tag-wise), just in debt.
                                new_temp = False
                                
                            if best_server['id'] != user.get('allocated_server_id') or (user.get('is_temporary_server') and not new_temp) or (user.get('is_in_debt') and not new_in_debt):
                                safe_prefix = user.get('email', '').replace('@', '-').replace('.', '-')
                                subdomain = f"{safe_prefix}.{BASE_ZONE}"
                                
                                # Only update DNS if server changed
                                if best_server['id'] != user.get('allocated_server_id'):
                                    old_subdomain = user.get('allocated_subdomain')
                                    if old_subdomain and old_subdomain != subdomain:
                                        delete_dns_record(old_subdomain, DYNV6_TOKEN)
                                    delete_dns_record(subdomain, DYNV6_TOKEN)
                                    create_dns_record(subdomain, best_server['original_ip'], DYNV6_TOKEN)
                                        
                                db.collection('users').document(user_id).update({
                                    'allocated_server_id': best_server['id'],
                                    'allocated_subdomain': subdomain,
                                    'is_temporary_server': new_temp,
                                    'is_in_debt': new_in_debt
                                })
                                print(f"Auto-recovered user {user.get('email')} to server {best_server['id']} (temp={new_temp}, debt={new_in_debt})")
                except Exception as e:
                    print(f"Error processing user {user_id} in background task: {e}")
                    continue
        except Exception as e:
            print(f"Background expiry checker error: {e}")
            
        time.sleep(15)

def keep_alive():
    """
    Pings the server every 10 minutes to prevent Render's free tier from sleeping.
    """
    while True:
        time.sleep(10 * 60)  # Sleep 10 minutes
        try:
            requests.get('https://bombavpn.onrender.com', timeout=10)
            print("Self-ping successful: Kept server awake.")
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
                    'created_at': datetime.utcnow()
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
                    'created_at': datetime.utcnow()
                }
                db.collection('purchase_requests').add(req_data)
                reqs_count += 1
                
    return f"Migrated {subs_count} active subscriptions and {reqs_count} pending requests."

if __name__ == '__main__':
    # Start the Keep-Alive thread
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
