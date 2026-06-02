import re
import json
import base64
import urllib.parse

def is_base64(s):
    try:
        # Check if the string can be decoded as base64 and re-encoded back to the same string
        return base64.b64encode(base64.b64decode(s)).decode('utf-8') == s or base64.b64encode(base64.b64decode(s + "=" * (-len(s) % 4))).decode('utf-8') == s + "=" * (-len(s) % 4)
    except Exception:
        return False

def parse_vless_uri(uri):
    """
    Parses a single vless:// URI and converts it to a standard Xray JSON configuration.
    """
    try:
        if not uri.startswith('vless://'):
            return None

        # Extract UUID, Address, Port, and Query Params
        # vless://uuid@host:port?param1=value1&param2=value2#Name
        
        # Remove vless:// prefix
        uri_body = uri[8:]
        
        # Split Name (hash)
        name_split = uri_body.split('#', 1)
        name = urllib.parse.unquote(name_split[1]) if len(name_split) > 1 else "Unknown Server"
        uri_body = name_split[0]
        
        # Split query params
        query_split = uri_body.split('?', 1)
        query_string = query_split[1] if len(query_split) > 1 else ""
        uri_body = query_split[0]
        
        # Split uuid and host:port
        auth_split = uri_body.split('@', 1)
        if len(auth_split) != 2:
            return None
            
        uuid = auth_split[0]
        host_port = auth_split[1]
        
        # Split host and port
        hp_split = host_port.split(':', 1)
        host = hp_split[0]
        port = int(hp_split[1]) if len(hp_split) > 1 else 443
        
        # Parse query params
        params = dict(urllib.parse.parse_qsl(query_string))
        
        # Build Stream Settings
        stream_settings = {
            "network": params.get('type', 'tcp'),
            "security": params.get('security', 'none'),
        }
        
        # TLS / REALITY settings
        if stream_settings["security"] == "tls":
            stream_settings["tlsSettings"] = {
                "serverName": params.get('sni', host),
                "fingerprint": params.get('fp', 'chrome')
            }
        elif stream_settings["security"] == "reality":
            stream_settings["realitySettings"] = {
                "serverName": params.get('sni', host),
                "fingerprint": params.get('fp', 'chrome'),
                "publicKey": params.get('pbk', ''),
                "shortId": params.get('sid', ''),
                "spiderX": params.get('spx', '/')
            }
            
        # Network specifics
        network_type = stream_settings["network"]
        if network_type == "ws":
            stream_settings["wsSettings"] = {
                "path": params.get('path', '/'),
                "headers": {
                    "Host": params.get('host', params.get('sni', host))
                }
            }
        elif network_type == "grpc":
            stream_settings["grpcSettings"] = {
                "serviceName": params.get('serviceName', ''),
                "multiMode": params.get('mode', 'multi') == 'multi'
            }
        elif network_type == "tcp":
            if params.get('headerType') == 'http':
                stream_settings["tcpSettings"] = {
                    "header": {
                        "type": "http",
                        "request": {
                            "version": "1.1",
                            "method": "GET",
                            "path": ["/"],
                            "headers": {
                                "Host": [params.get('host', params.get('sni', host))],
                                "User-Agent": ["Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.75 Safari/537.36"]
                            }
                        }
                    }
                }
        
        # Build Final JSON
        config = {
            "remarks": name,
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": host,
                                "port": port,
                                "users": [
                                    {
                                        "id": uuid,
                                        "encryption": params.get('encryption', 'none'),
                                        "flow": params.get('flow', '')
                                    }
                                ]
                            }
                        ]
                    },
                    "streamSettings": stream_settings
                }
            ]
        }
        
        return config
        
    except Exception as e:
        print(f"Error parsing VLESS URI {uri}: {e}")
        return None

def extract_vless_from_text(text):
    """
    Given a block of text (which could be raw or base64 encoded),
    returns a list of parsed JSON configs.
    """
    text = text.strip()
    
    # Check if it's base64 encoded
    # V2Ray subscriptions are typically base64 encoded without padding
    try:
        padding_needed = len(text) % 4
        if padding_needed:
            padded_text = text + "=" * (4 - padding_needed)
        else:
            padded_text = text
            
        decoded_bytes = base64.b64decode(padded_text)
        decoded_text = decoded_bytes.decode('utf-8')
        
        # If the decoded text contains 'vless://', we consider it a successful decode
        if 'vless://' in decoded_text:
            text = decoded_text
    except Exception:
        pass
        
    # Now extract all vless:// links
    links = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('vless://'):
            links.append(line)
            
    # Parse them
    configs = []
    for link in links:
        parsed = parse_vless_uri(link)
        if parsed:
            configs.append(parsed)
            
    return configs
