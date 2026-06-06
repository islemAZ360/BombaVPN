import os
import requests
import urllib.parse
import socket
import ipaddress
import json
from datetime import datetime, timedelta, timezone
from flask import request
from extensions import current_app
from supabase_client import supabase_admin as db
from db_helpers import get_all_users, get_all_servers, get_all_messages, get_all_subscriptions, get_all_pricing_rules, get_all_source_links
from utils import extract_ip_from_json, extract_name_from_json
from vless_parser import extract_vless_from_text
from translations import TRANSLATIONS

def get_translation(key, *args):
    lang = request.cookies.get('lang')
    if not lang or lang not in TRANSLATIONS:
        lang = request.accept_languages.best_match(TRANSLATIONS.keys()) or 'ar'
    text = TRANSLATIONS[lang].get(key, key)
    if args:
        text = text.format(*args)
    return text


def send_telegram_notification(message):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception as e:
            print(f"Telegram notification failed: {e}")

def send_telegram_receipt_review(req_id, user_email, server_name, receipt_filename, price):
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], receipt_filename)
            
            caption = f"💳 <b>New Payment Receipt!</b>\n\n" \
                      f"👤 <b>User:</b> <code>{user_email}</code>\n" \
                      f"💻 <b>Server:</b> {server_name}\n" \
                      f"💰 <b>Price:</b> {price} ₽\n\n" \
                      f"Please review the receipt image and approve or reject."
                      
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"approve_{req_id}"},
                        {"text": "❌ Reject", "callback_data": f"reject_{req_id}"}
                    ]
                ]
            }
            
            if os.path.exists(file_path):
                with open(file_path, 'rb') as photo:
                    files = {'photo': photo}
                    data = {
                        'chat_id': chat_id, 
                        'caption': caption, 
                        'parse_mode': 'HTML',
                        'reply_markup': json.dumps(reply_markup)
                    }
                    response = requests.post(url, files=files, data=data, timeout=15)
                    response.raise_for_status()
            else:
                # Fallback to text if file missing
                send_telegram_notification(caption)
    except Exception as e:
        error_msg = str(e)
        print(f"Telegram receipt review failed: {error_msg}")
        try:
            from supabase_client import supabase_admin
            supabase_admin.table('notifications').insert({
                'title': 'Telegram API Error',
                'body': f'Failed to send receipt photo for request {req_id}. Error: {error_msg}',
                'type': 'danger',
                'is_read': False
            }).execute()
        except Exception as db_e:
            print(f"Failed to save error notification: {db_e}")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=total_real_seconds)

    resp = db.table('servers').select('*').execute()
    existing_docs = resp.data if resp.data else []
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

            plan_days_equiv = total_plan_seconds // 86400
            matched_rules = []
            for rule in pricing_rules:
                if rule['tags'].issubset(keywords_lower) and rule.get('duration_days', 0) == plan_days_equiv:
                    matched_rules.append(rule)

            if matched_rules:
                # Prioritize the rule with the most matching tags (highest specificity)
                best_rule = max(matched_rules, key=lambda r: len(r['tags']))
                final_price = best_rule['price']

            existing_servers.append(final_name)
            if original_link:
                existing_links.add(original_link)

            # Generate ID manually or let DB handle it? Assuming Supabase will generate if omitted, wait, schema says 'id TEXT PRIMARY KEY', so we might need uuid.
            import uuid
            db.table('servers').insert({
                'id': str(uuid.uuid4()),
                'name': final_name,
                'source_link_id': source_link_id,
                'original_ip': ip,
                'country_code': cc.lower() if cc else None,
                'json_config': content,
                'vless_link': original_link,
                'price': float(final_price),
                'total_plan_seconds': total_plan_seconds,
                'plan_minutes': plan_minutes,
                'tags': keywords,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': expires_at.isoformat() if expires_at else None
            }).execute()
            added += 1

    return len(parsed_configs), added

def _approve_request_logic(request_id):
    req_resp = db.table('purchase_requests').select('*').eq('id', request_id).execute()
    if not req_resp.data or req_resp.data[0].get('status') != 'pending':
        return False, "Request not found or not pending"
        
    req_data = req_resp.data[0]
    user_id = req_data['user_id']
    server_id = req_data['server_id']
    
    user_resp = db.table('users').select('*').eq('id', user_id).execute()
    if not user_resp.data:
        return False, "User not found"
    user_data = user_resp.data[0]
        
    days = 30
    hours = 0
    minutes = 0
    s_data = None
        
    server_resp = db.table('servers').select('*').eq('id', server_id).execute()
    if server_resp.data:
        s_data = server_resp.data[0]
        days = int(s_data.get('plan_days') or 0)
        hours = int(s_data.get('plan_hours') or 0)
        minutes = int(s_data.get('plan_minutes') or 0)
        
        if not days and not hours and not minutes:
            days = 30
        
    duration_delta = timedelta(days=days, hours=hours, minutes=minutes)
    expires_at = datetime.now(timezone.utc) + duration_delta
    
    if s_data:
        s_expires_str = s_data.get('expires_at')
        if s_expires_str:
            s_expires = datetime.fromisoformat(s_expires_str.replace('Z', '+00:00'))
            if s_expires < expires_at:
                debt_delta = expires_at - s_expires
                import uuid
                db.table('notifications').insert({
                    'id': str(uuid.uuid4()),
                    'title': 'تنبيه ديون / Debt Alert',
                    'message': f'المستخدم / User {user_data.get("email")} لديه اشتراك يتجاوز عمر السيرفر المختار. نظام النقل التلقائي سيتدخل لاحقاً ليكمل الـ {debt_delta.days} يوم المتبقية.',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'is_read': False,
                    'type': 'debt'
                }).execute()
    
    import uuid
    sub_id = str(uuid.uuid4())
    db.table('subscriptions').insert({
        'id': sub_id,
        'user_id': user_id,
        'server_id': server_id,
        'original_server_id': server_id,
        'allocated_subdomain': None,
        'status': 'active',
        'required_tags': s_data.get('tags', []) if s_data else [],
        'is_temporary': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'expires_at': expires_at.isoformat()
    }).execute()
    
    receipt_image = req_data.get('receipt_url')
    if receipt_image:
        try: os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], receipt_image))
        except OSError: pass
        
    db.table('purchase_requests').update({'status': 'approved'}).eq('id', request_id).execute()
    
    if user_data.get('status') != 'active':
        db.table('users').update({'status': 'active'}).eq('id', user_id).execute()
        
    if user_data.get('referred_by'):
        referrer_code = user_data['referred_by']
        referrer_resp = db.table('users').select('*').eq('referral_code', referrer_code).limit(1).execute()
        if referrer_resp.data:
            r_user = referrer_resp.data[0]
            r_user_id = r_user['id']
            all_r_subs_resp = db.table('subscriptions').select('*').eq('user_id', r_user_id).execute()
            all_r_subs = all_r_subs_resp.data if all_r_subs_resp.data else []
            
            new_sub_expiry = expires_at + timedelta(days=7)
            db.table('subscriptions').update({'expires_at': new_sub_expiry.isoformat()}).eq('id', sub_id).execute()
            
            if not all_r_subs:
                send_telegram_notification(f"⚠️ إحالة بدون مكافأة!\nالمستخدم {user_data.get('email')} اشترى عبر الرابط.")
            else:
                active_subs = [d for d in all_r_subs if d.get('status') == 'active']
                if active_subs:
                    latest_active = max(active_subs, key=lambda d: datetime.fromisoformat(d['expires_at'].replace('Z', '+00:00')) if d.get('expires_at') else datetime.min.replace(tzinfo=timezone.utc))
                    r_sub = latest_active
                    if r_sub.get('expires_at'):
                        exp_dt = datetime.fromisoformat(r_sub['expires_at'].replace('Z', '+00:00'))
                        new_expiry = exp_dt + timedelta(days=7)
                        db.table('subscriptions').update({'expires_at': new_expiry.isoformat()}).eq('id', latest_active['id']).execute()
                    send_telegram_notification(f"🎉 مكافأة إحالة!\nالمستخدم {user_data.get('email')} اشترى باقة.")
                else:
                    expired_subs = [d for d in all_r_subs if d.get('status') == 'expired']
                    if expired_subs:
                        latest_expired = max(expired_subs, key=lambda d: datetime.fromisoformat(d['expires_at'].replace('Z', '+00:00')) if d.get('expires_at') else datetime.min.replace(tzinfo=timezone.utc))
                        new_expiry = datetime.now(timezone.utc) + timedelta(days=7)
                        db.table('subscriptions').update({
                            'status': 'active',
                            'expires_at': new_expiry.isoformat()
                        }).eq('id', latest_expired['id']).execute()
                        send_telegram_notification(f"🎉 مكافأة إحالة!\nتفعيل اشتراك منتهي.")
        
        # Remove referred_by
        db.table('users').update({'referred_by': None}).eq('id', user_id).execute()
        
    return True, "Success"

def _reject_request_logic(request_id):
    req_resp = db.table('purchase_requests').select('*').eq('id', request_id).execute()
    
    if req_resp.data:
        req_data = req_resp.data[0]
        if req_data.get('status') != 'pending':
            return False, "Not pending"
            
        receipt_image = req_data.get('receipt_url')
        if receipt_image:
            try: os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], receipt_image))
            except OSError: pass
            
        db.table('purchase_requests').update({'status': 'rejected'}).eq('id', request_id).execute()
        return True, "Success"
    return False, "Not found"
