import os
import threading
import functools
from flask import request, redirect, url_for, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
from itsdangerous import URLSafeSerializer

# Limiter Initialization
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://"
)

# Firebase Init
db = None
FIREBASE_READY = False

# Serializer for secure tokens
sub_serializer = URLSafeSerializer(os.environ.get('SECRET_KEY', 'bomba_vpn_fallback_secret_key_12345'))
try:
    cred = credentials.Certificate("firebase-adminsdk.json")
    if not firebase_admin._apps:
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
            return redirect(url_for('auth.login'))
            
        try:
            decoded_claims = firebase_auth.verify_session_cookie(session_cookie, check_revoked=False)
            request.user = decoded_claims
            request.is_admin = (decoded_claims.get('email') == 'islamazaizia360@gmail.com')
        except Exception as e:
            is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'
            if not is_production:
                try:
                    from itsdangerous import URLSafeTimedSerializer
                    local_serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
                    data = local_serializer.loads(session_cookie, max_age=5*24*3600)
                    if data.get('is_local_session'):
                        request.user = {'uid': data['uid'], 'email': data['email'], 'name': data.get('name', '')}
                        request.is_admin = (data.get('email') == 'islamazaizia360@gmail.com')
                        return f(*args, **kwargs)
                except Exception:
                    pass
            print(f"Session verification failed: {e}")
            return redirect(url_for('auth.login'))
            
        return f(*args, **kwargs)
    return decorated_function
