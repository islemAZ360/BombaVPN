import os
import threading
import time
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for

from extensions import limiter
from db_helpers import get_all_users, get_all_servers, get_all_messages, get_all_subscriptions, get_all_pricing_rules, get_all_source_links

# Import the Blueprints
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.api_routes import api_bp
from routes.main_routes import main_bp

from translations import TRANSLATIONS
from worker import background_expiry_checker

app = Flask(__name__)

thread_started = False
thread_lock = threading.Lock()

# Security config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bomba_vpn_fallback_secret_key_12345')
app.config['SESSION_COOKIE_NAME'] = 'flask_session'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Limiter with app
limiter.init_app(app)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(main_bp)


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

@app.context_processor
def inject_notifications():
    count = 0
    if getattr(request, 'is_admin', False):
        try:
            from supabase_client import supabase_admin
            resp = supabase_admin.table('notifications').select('*', count='exact').eq('is_read', False).execute()
            count = resp.count if resp.count else 0
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


# ---------------------------------------------------------
# CUSTOM ERROR HANDLERS
# ---------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


# ---------------------------------------------------------
# BACKGROUND THREAD
# ---------------------------------------------------------


@app.before_request
def before_request_handler():
    try:
        from datetime import datetime
        with open('debug_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] REQUEST HIT: {request.method} {request.url}\\n")
    except:
        pass
        
    if request.method == 'POST' and request.endpoint not in ['api.ping', 'api.debug_check', 'auth.session_login', 'api.telegram_webhook', 'api.setup_telegram_webhook']:
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
                except Exception as e:
                    print("Could not start background thread:", e)

                # Register the Telegram webhook once so Approve/Reject buttons work
                # without anyone opening the admin page. Uses the public Render URL
                # (RENDER_EXTERNAL_URL) and falls back to the request host (forced to
                # https, since Telegram requires it).
                try:
                    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
                    if bot_token:
                        base = os.environ.get('RENDER_EXTERNAL_URL') or request.host_url
                        base = base.rstrip('/').replace('http://', 'https://')
                        webhook_url = base + '/api/telegram/webhook'
                        import requests as _requests
                        _requests.post(
                            f"https://api.telegram.org/bot{bot_token}/setWebhook",
                            json={'url': webhook_url, 'allowed_updates': ['callback_query', 'message']},
                            timeout=10
                        )
                        print(f"Telegram webhook registered: {webhook_url}")
                except Exception as e:
                    print("Could not register Telegram webhook:", e)

                thread_started = True


@app.after_request
def add_header(response):
    if 'Cache-Control' not in response.headers:
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)
