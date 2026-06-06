
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
from helpers import *

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login():
    return render_template('login.html')

@auth_bp.route('/register')
def register():
    return redirect(url_for('auth.login'))

@auth_bp.route('/api/sessionLogin', methods=['POST'])
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
                'created_at': datetime.now(timezone.utc),
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
                local_serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
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

@auth_bp.route('/api/sessionLogout', methods=['POST'])
def session_logout():
    response = jsonify({'status': 'success'})
    response.set_cookie('session', '', expires=0)
    return response
