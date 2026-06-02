import logging
import requests

logger = logging.getLogger(__name__)

def get_zone_id(base_zone, token):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        resp = requests.get('https://dynv6.com/api/v2/zones', headers=headers, timeout=10)
        if resp.status_code == 200:
            zones = resp.json()
            for z in zones:
                if z.get('name') == base_zone:
                    return z.get('id')
    except Exception as e:
        logger.error(f"Error fetching zones: {e}")
    return None

def create_dns_record(subdomain, ipv4_address, token):
    if token == "YOUR_DYNV6_TOKEN_HERE" or not token:
        logger.warning(f"[MOCK] Token not set. Mocking DNS record creation {subdomain} -> {ipv4_address}")
        return False

    parts = subdomain.split('.')
    record_name = parts[0]
    base_zone = '.'.join(parts[1:])

    zone_id = get_zone_id(base_zone, token)
    if not zone_id:
        logger.error(f"Could not find zone_id for {base_zone}")
        return False

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'Content-Type': 'application/json'}
    
    try:
        # First check if record exists
        resp = requests.get(f'https://dynv6.com/api/v2/zones/{zone_id}/records', headers=headers, timeout=10)
        if resp.status_code == 200:
            records = resp.json()
            for r in records:
                if r.get('name') == record_name:
                    if r.get('data') == ipv4_address:
                        return True
                    # Update existing record
                    patch_resp = requests.patch(f"https://dynv6.com/api/v2/zones/{zone_id}/records/{r.get('id')}", json={'data': ipv4_address}, headers=headers, timeout=10)
                    return patch_resp.status_code == 200

        # Create new record
        data = {
            "name": record_name,
            "type": "A",
            "data": ipv4_address
        }
        post_resp = requests.post(f'https://dynv6.com/api/v2/zones/{zone_id}/records', json=data, headers=headers, timeout=10)
        return post_resp.status_code == 200
    except Exception as e:
        logger.error(f"Error creating DNS record: {e}")
        return False

def delete_dns_record(subdomain, token):
    if token == "YOUR_DYNV6_TOKEN_HERE" or not token:
        logger.warning(f"[MOCK] Token not set. Mocking DNS deletion {subdomain}")
        return False

    parts = subdomain.split('.')
    record_name = parts[0]
    base_zone = '.'.join(parts[1:])

    zone_id = get_zone_id(base_zone, token)
    if not zone_id:
        return False

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        resp = requests.get(f'https://dynv6.com/api/v2/zones/{zone_id}/records', headers=headers, timeout=10)
        if resp.status_code == 200:
            records = resp.json()
            for r in records:
                if r.get('name') == record_name:
                    del_resp = requests.delete(f"https://dynv6.com/api/v2/zones/{zone_id}/records/{r.get('id')}", headers=headers, timeout=10)
                    return del_resp.status_code == 200
    except Exception as e:
        logger.error(f"Error deleting DNS record: {e}")
    return False
