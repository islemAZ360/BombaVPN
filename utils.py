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
