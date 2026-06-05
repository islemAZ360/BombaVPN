import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add source_links_cache definition
cache_code = """
source_links_cache = {}
source_links_cache_lock = threading.Lock()

def on_source_links_snapshot(col_snapshot, changes, read_time):
    with source_links_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                source_links_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                source_links_cache.pop(change.document.id, None)
"""

if "source_links_cache =" not in content:
    content = content.replace("pricing_rules_cache = {}", cache_code + "\npricing_rules_cache = {}")

# 2. Add listener registration in before_request
listen_code = "db.collection('source_links').on_snapshot(on_source_links_snapshot)"
if listen_code not in content:
    content = content.replace("db.collection('pricing_rules').on_snapshot(on_pricing_rules_snapshot)", 
                              "db.collection('pricing_rules').on_snapshot(on_pricing_rules_snapshot)\n                    " + listen_code)

# 3. Modify dashboard_sync to include source_links
dashboard_sync_old = "return jsonify({'users': all_users, 'servers': all_servers, 'active_users': active_users})"
dashboard_sync_new = """
    links = []
    with source_links_cache_lock:
        for l_id, l_dict in source_links_cache.items():
            l = l_dict.copy()
            l['id'] = l_id
            if isinstance(l.get('created_at'), datetime):
                l['created_at'] = l['created_at'].isoformat()
            links.append(l)
    return jsonify({'users': all_users, 'servers': all_servers, 'active_users': active_users, 'source_links': links})
"""
if dashboard_sync_old in content:
    content = content.replace(dashboard_sync_old, dashboard_sync_new)

# 4. Modify import_servers to save source link
import_servers_old = """    # If the text is a URL, fetch it
    if subscription_text.startswith('http://') or subscription_text.startswith('https://'):
        try:
            resp = requests.get(subscription_text, timeout=10, headers={'User-Agent': 'v2rayNG'})"""
import_servers_new = """    source_link_id = None
    original_url = subscription_text
    
    # If the text is a URL, fetch it
    if subscription_text.startswith('http://') or subscription_text.startswith('https://'):
        try:
            # Save to source_links
            doc_ref = db.collection('source_links').add({
                'url': original_url,
                'plan_days': plan_days,
                'plan_hours': plan_hours,
                'plan_minutes': plan_minutes,
                'real_days': real_days,
                'real_hours': real_hours,
                'real_minutes': real_minutes,
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
            })
            source_link_id = doc_ref[1].id
            
            resp = requests.get(subscription_text, timeout=10, headers={'User-Agent': 'v2rayNG'})"""
if import_servers_old in content and "source_link_id = None" not in content:
    content = content.replace(import_servers_old, import_servers_new)

add_server_old = """            db.collection('servers').add({
                'name': final_name,"""
add_server_new = """            db.collection('servers').add({
                'name': final_name,
                'source_link_id': source_link_id,"""
if add_server_old in content and "source_link_id" not in add_server_old:
    content = content.replace(add_server_old, add_server_new)

# 5. Add sync_link and delete_link endpoints
api_code = """
@app.route('/api/admin/delete_link/<link_id>', methods=['POST'])
@login_required
def delete_link(link_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    db.collection('source_links').document(link_id).delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/sync_link/<link_id>', methods=['POST'])
@login_required
def sync_link(link_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    link_data = None
    with source_links_cache_lock:
        if link_id in source_links_cache:
            link_data = source_links_cache[link_id].copy()
            
    if not link_data:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Link not found'}), 404
        flash('Link not found', 'error')
        return redirect(url_for('admin_dashboard'))
        
    url = link_data.get('url')
    plan_days = int(link_data.get('plan_days') or 0)
    real_days = int(link_data.get('real_days') or 0)
    real_hours = int(link_data.get('real_hours') or 0)
    real_minutes = int(link_data.get('real_minutes') or 0)
    
    if real_days == 0 and real_hours == 0 and real_minutes == 0:
        expires_at = None
    else:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=real_days, hours=real_hours, minutes=real_minutes)
        
    try:
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'v2rayNG'})
        if resp.status_code != 200:
            return jsonify({'error': f'Failed to fetch link: {resp.status_code}'}), 400
        subscription_text = resp.text
    except Exception as e:
        return jsonify({'error': f'Error fetching link: {e}'}), 400
        
    parsed_configs = extract_vless_from_text(subscription_text)
    if not parsed_configs:
        return jsonify({'error': 'No VLESS configs found in link'}), 400
        
    # Get current pricing rules
    rules = []
    with pricing_rules_cache_lock:
        for r_id, r_dict in pricing_rules_cache.items():
            r = r_dict.copy()
            r['tags'] = set(r.get('tags', []))
            rules.append(r)
            
    # Get existing IPs to avoid duplicates, and existing server data
    existing_servers = {}
    with servers_cache_lock:
        for s_id, s_dict in servers_cache.items():
            if s_dict.get('original_ip'):
                existing_servers[s_dict['original_ip']] = {'id': s_id, 'data': s_dict}
                
    config_data_list = []
    ips_to_query = []
    for config_dict in parsed_configs:
        original_link = config_dict.pop('_original_link', '')
        content_json = json.dumps(config_dict, ensure_ascii=False)
        ip = extract_ip_from_json(content_json)
        config_data_list.append((config_dict, content_json, ip, original_link))
        if ip:
            ips_to_query.append(ip)
            
    country_map = get_country_info_bulk(ips_to_query)
    
    added = 0
    updated = 0
    
    for config_dict, content_json, ip, original_link in config_data_list:
        if not ip: continue
        
        orig_name = extract_name_from_json(content_json) or "Imported Server"
        
        # Recalculate tags
        new_tags = []
        name_no_dash = orig_name.lower().replace('-', ' ').replace('_', ' ').replace('|', ' ')
        words = name_no_dash.split()
        if 'gemini' in orig_name.lower(): new_tags.append('gemini')
        if 'youtube' in orig_name.lower() or 'yt' in words: new_tags.append('yt')
        if 'lte' in orig_name.lower(): new_tags.append('lte')
        if 'russia' in orig_name.lower() or 'ru' in words: new_tags.append('ru')
        if 'torrent' in orig_name.lower(): new_tags.append('torrent')
        new_tags_set = set(new_tags)
        
        # Match rule
        final_price = 0
        matched_rules = []
        for rule in rules:
            if rule['tags'].issubset(new_tags_set) and rule.get('duration_days', 0) == plan_days:
                matched_rules.append(rule)
        if matched_rules:
            best_rule = max(matched_rules, key=lambda r: len(r['tags']))
            final_price = best_rule['price']
            
        country_name, cc = country_map.get(ip, ("Unknown", None))
        if country_name == "Unknown":
            if 'ru' in words or 'russia' in orig_name.lower(): cc = "RU"
            elif 'de' in words or 'germany' in orig_name.lower(): cc = "DE"
            elif 'ee' in words or 'estonia' in orig_name.lower(): cc = "EE"
            elif 'lv' in words or 'latvia' in orig_name.lower(): cc = "LV"
            elif 'nl' in words or 'netherlands' in orig_name.lower(): cc = "NL"
            elif 'fr' in words or 'france' in orig_name.lower(): cc = "FR"
            elif 'gb' in words or 'uk' in words: cc = "GB"
            elif 'us' in words or 'usa' in words: cc = "US"
            
        if ip in existing_servers:
            # Update
            s_id = existing_servers[ip]['id']
            db.collection('servers').document(s_id).update({
                'name': orig_name,
                'tags': new_tags,
                'price': final_price,
                'json_config': content_json,
                'vless_link': original_link,
                'source_link_id': link_id,
                'country_code': cc.lower() if cc else None
            })
            updated += 1
        else:
            # Add new
            db.collection('servers').add({
                'name': orig_name,
                'original_ip': ip,
                'country_code': cc.lower() if cc else None,
                'json_config': content_json,
                'vless_link': original_link,
                'price': final_price,
                'plan_days': plan_days,
                'plan_hours': int(link_data.get('plan_hours') or 0),
                'plan_minutes': int(link_data.get('plan_minutes') or 0),
                'tags': new_tags,
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None),
                'expires_at': expires_at,
                'source_link_id': link_id
            })
            added += 1
            
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'added': added, 'updated': updated})
    flash(f'Sync Complete! Added {added}, Updated {updated}', 'success')
    return redirect(url_for('admin_dashboard'))
"""

if "@app.route('/api/admin/delete_link/<link_id>'" not in content:
    target_str = "@app.route('/api/admin/rescan_servers')"
    content = content.replace(target_str, api_code + "\n\n" + target_str)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Source links backend applied successfully.")
