import json

def modify_json_address(original_json_str, new_address):
    """
    Parses the JSON, finds the outbounds -> vless/vmess -> address,
    and replaces it with the new_address (the subdomain).
    """
    try:
        data = json.loads(original_json_str)
        # Find the proxy outbound
        for outbound in data.get('outbounds', []):
            if outbound.get('protocol') in ['vless', 'vmess', 'trojan']:
                settings = outbound.get('settings', {})
                vnext = settings.get('vnext', [])
                if vnext and len(vnext) > 0:
                    vnext[0]['address'] = new_address
                    return json.dumps(data, indent=4)
        return original_json_str # Fallback if not found
    except Exception as e:
        print(f"Error modifying JSON: {e}")
        return original_json_str

def extract_ip_from_json(json_str):
    """Extracts the real IP from the JSON config"""
    try:
        data = json.loads(json_str)
        for outbound in data.get('outbounds', []):
             if outbound.get('protocol') in ['vless', 'vmess', 'trojan']:
                settings = outbound.get('settings', {})
                vnext = settings.get('vnext', [])
                if vnext and len(vnext) > 0:
                    return vnext[0].get('address')
        return None
    except:
        return None

import re

def extract_name_from_json(json_str):
    """Extracts the name/remarks from the JSON config"""
    def clean_name(text):
        if not text: return text
        # Remove flag emojis
        text = re.sub(r'[\U0001F1E6-\U0001F1FF]', '', text)
        # Remove other weird symbols/emojis, keep letters, numbers, spaces, and basic punctuation
        text = re.sub(r'[^\w\s\-\.\|#\(\)]', '', text)
        # Clean up multiple spaces or leading/trailing separators
        text = re.sub(r'\s+', ' ', text)
        return text.strip(' |-#')

    try:
        data = json.loads(json_str)
        # Some configs use 'remarks' at root level
        if 'remarks' in data:
            return clean_name(data['remarks'])
            
        # Or look into outbounds tag
        for outbound in data.get('outbounds', []):
             if outbound.get('protocol') in ['vless', 'vmess', 'trojan']:
                 tag = outbound.get('tag')
                 if tag and tag.lower() != 'proxy':
                     return clean_name(tag)
                     
        return None
    except:
        return None

import urllib.parse

def generate_vless_uri(json_str, active_address=None):
    try:
        data = json.loads(json_str)
        name = data.get('remarks', 'BombaVPN')
        
        for outbound in data.get('outbounds', []):
            if outbound.get('protocol') == 'vless':
                settings = outbound.get('settings', {})
                vnext = settings.get('vnext', [])
                if not vnext: continue
                
                server = vnext[0]
                address = active_address if active_address else server.get('address')
                port = server.get('port')
                users = server.get('users', [])
                if not users: continue
                uuid = users[0].get('id')
                flow = users[0].get('flow', '')
                encryption = users[0].get('encryption', 'none')
                
                stream = outbound.get('streamSettings', {})
                network = stream.get('network', 'tcp')
                security = stream.get('security', 'none')
                
                params = {
                    'type': network,
                    'security': security,
                }
                if encryption and encryption != 'none':
                    params['encryption'] = encryption
                if flow:
                    params['flow'] = flow
                
                # Security Settings
                if security == 'tls':
                    tls = stream.get('tlsSettings', {})
                    if tls.get('serverName'): params['sni'] = tls.get('serverName')
                    if tls.get('fingerprint'): params['fp'] = tls.get('fingerprint')
                    if tls.get('alpn'):
                        alpn = tls.get('alpn')
                        if isinstance(alpn, list): params['alpn'] = ','.join(alpn)
                        else: params['alpn'] = alpn
                elif security == 'reality':
                    reality = stream.get('realitySettings', {})
                    if reality.get('serverName'): params['sni'] = reality.get('serverName')
                    if reality.get('fingerprint'): params['fp'] = reality.get('fingerprint')
                    if reality.get('publicKey'): params['pbk'] = reality.get('publicKey')
                    if reality.get('shortId'): params['sid'] = reality.get('shortId')
                    if reality.get('spiderX'): params['spx'] = reality.get('spiderX')
                
                # Network Settings
                if network == 'ws':
                    ws = stream.get('wsSettings', {})
                    if ws.get('path'): params['path'] = ws.get('path')
                    headers = ws.get('headers', {})
                    if headers.get('Host'): params['host'] = headers.get('Host')
                elif network == 'grpc':
                    grpc = stream.get('grpcSettings', {})
                    if grpc.get('serviceName'): params['serviceName'] = grpc.get('serviceName')
                    if grpc.get('multiMode'): params['mode'] = 'multi'
                elif network == 'tcp':
                    tcp = stream.get('tcpSettings', {})
                    header = tcp.get('header', {})
                    if header.get('type') == 'http':
                        params['headerType'] = 'http'
                        req = header.get('request', {})
                        headers = req.get('headers', {})
                        if headers.get('Host'):
                            h = headers.get('Host')
                            params['host'] = h[0] if isinstance(h, list) else h
                
                query = urllib.parse.urlencode(params)
                name_encoded = urllib.parse.quote(name)
                
                return f"vless://{uuid}@{address}:{port}?{query}#{name_encoded}"
                
        return None
    except Exception as e:
        print(f"Error generating VLESS URI: {e}")
        return None
