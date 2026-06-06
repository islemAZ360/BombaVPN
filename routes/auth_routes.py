from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app
from datetime import datetime, timedelta, timezone
import os
from extensions import limiter, login_required
from supabase_client import supabase, supabase_admin

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login():
    return render_template('login.html', 
                           supabase_url=os.environ.get("SUPABASE_URL"), 
                           supabase_anon_key=os.environ.get("SUPABASE_KEY"))

@auth_bp.route('/register')
def register():
    return redirect(url_for('auth.login'))

@auth_bp.route('/api/sessionLogin', methods=['POST'])
@limiter.limit("5 per minute")
def session_login():
    access_token = request.json.get('access_token')
    ref_code = request.json.get('ref_code')
    expires_in = timedelta(days=5)
    is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER') == 'true'
    
    try:
        # Get user from Supabase auth using the token
        user_resp = supabase.auth.get_user(access_token)
        if not user_resp or not user_resp.user:
            return jsonify({'error': 'Invalid token'}), 401
            
        user = user_resp.user
        uid = user.id
        email = user.email
        
        # Check if user exists in public.users
        user_data_resp = supabase_admin.table('users').select('*').eq('id', uid).execute()
        
        if not user_data_resp.data:
            is_new_user = True
            # Create new user in public.users
            new_user_data = {
                'id': uid,
                'email': email,
                'status': 'pending',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'referral_code': uid[:8],
            }
            if ref_code and ref_code != uid[:8]:
                new_user_data['referred_by'] = ref_code
            supabase_admin.table('users').insert(new_user_data).execute()
        else:
            is_new_user = False
        
        # In Supabase, the client manages the session token (access_token/refresh_token)
        # But we still want a server-side cookie for Flask routes (@login_required)
        # We will store the access_token in the cookie
        response = jsonify({'status': 'success', 'is_new_user': is_new_user})
        expires = datetime.now() + expires_in
        response.set_cookie('session', access_token, expires=expires, httponly=True, secure=is_production, samesite='Lax')
        return response
    except Exception as e:
        print(f"Session login error: {type(e).__name__}: {e}")
        return jsonify({'error': str(e)}), 401

@auth_bp.route('/api/sessionLogout', methods=['POST'])
def session_logout():
    response = jsonify({'status': 'success'})
    response.set_cookie('session', '', expires=0)
    return response
