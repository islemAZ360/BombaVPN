import os
import functools
from flask import request, redirect, url_for, current_app, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeSerializer
from supabase_client import supabase_admin

# Limiter Initialization
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://"
)

# Dummy references to prevent import errors in scripts

# Serializer for secure tokens
sub_serializer = URLSafeSerializer(os.environ.get('SECRET_KEY', 'bomba_vpn_fallback_secret_key_12345'))

# Auth Decorator
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        session_cookie = request.cookies.get('session')
        if not session_cookie:
            return redirect(url_for('auth.login'))

        try:
            # Check session cookie with Supabase
            user_resp = supabase_admin.auth.get_user(session_cookie)
            if user_resp and user_resp.user:
                email = user_resp.user.email
                request.user = {
                    'uid': user_resp.user.id,
                    'email': email,
                    'name': user_resp.user.user_metadata.get('full_name', '')
                }
                request.is_admin = (email == 'islamazaizia360@gmail.com')
            else:
                raise Exception("Invalid Supabase session")
        except Exception as e:
            print(f"Session verification failed: {e}")
            resp = make_response(redirect(url_for('auth.login')))
            resp.set_cookie('session', '', expires=0, path='/')
            return resp

        return f(*args, **kwargs)
    return decorated_function
