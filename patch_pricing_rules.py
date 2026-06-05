import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add pricing_rules_cache definition
cache_code = """
pricing_rules_cache = {}
pricing_rules_cache_lock = threading.Lock()

def on_pricing_rules_snapshot(col_snapshot, changes, read_time):
    with pricing_rules_cache_lock:
        for change in changes:
            if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
                pricing_rules_cache[change.document.id] = change.document.to_dict()
            elif change.type.name == 'REMOVED':
                pricing_rules_cache.pop(change.document.id, None)
"""

if "pricing_rules_cache =" not in content:
    content = content.replace("subscriptions_cache = {}", cache_code + "\nsubscriptions_cache = {}")

# 2. Add listener registration in before_request
listen_code = "db.collection('pricing_rules').on_snapshot(on_pricing_rules_snapshot)"
if listen_code not in content:
    content = content.replace("db.collection('subscriptions').on_snapshot(on_subscriptions_snapshot)", 
                              "db.collection('subscriptions').on_snapshot(on_subscriptions_snapshot)\n                    " + listen_code)

# 3. Add API endpoints
api_code = """
@app.route('/api/admin/pricing_rules', methods=['GET', 'POST'])
@login_required
def api_pricing_rules():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    if request.method == 'GET':
        rules = []
        with pricing_rules_cache_lock:
            for r_id, r_dict in pricing_rules_cache.items():
                r = r_dict.copy()
                r['id'] = r_id
                # convert sets or arrays
                if 'tags' in r and isinstance(r['tags'], set):
                    r['tags'] = list(r['tags'])
                rules.append(r)
        return jsonify({'rules': rules})
        
    if request.method == 'POST':
        tags_str = request.form.get('tags', '')
        duration_days = int(request.form.get('duration_days') or 0)
        price = float(request.form.get('price') or 0)
        
        tags_list = [tag.strip().lower() for tag in tags_str.split(',') if tag.strip()]
        
        db.collection('pricing_rules').add({
            'tags': tags_list,
            'duration_days': duration_days,
            'price': price,
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })
        
        # If AJAX, return json. Otherwise redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'success'})
        return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/pricing_rules/<rule_id>/delete', methods=['POST'])
@login_required
def delete_pricing_rule(rule_id):
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
    db.collection('pricing_rules').document(rule_id).delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/rescan_servers', methods=['POST'])
@login_required
def rescan_servers():
    if not getattr(request, 'is_admin', False):
        return jsonify({'error': 'Unauthorized'}), 403
        
    # Get all rules
    rules = []
    with pricing_rules_cache_lock:
        for r_id, r_dict in pricing_rules_cache.items():
            r = r_dict.copy()
            # tags might be stored as list in firestore
            r['tags'] = set(r.get('tags', []))
            rules.append(r)
            
    # Iterate all active servers
    updated_count = 0
    with servers_cache_lock:
        server_list = list(servers_cache.items())
        
    for s_id, s_dict in server_list:
        name = s_dict.get('name', '').lower()
        plan_days = s_dict.get('plan_days', 0)
        
        # Re-extract tags
        new_tags = []
        name_no_dash = name.replace('-', ' ').replace('_', ' ').replace('|', ' ')
        words = name_no_dash.split()
        
        if 'gemini' in name: new_tags.append('gemini')
        if 'youtube' in name or 'yt' in words: new_tags.append('yt')
        if 'lte' in name: new_tags.append('lte')
        if 'russia' in name or 'ru' in words: new_tags.append('ru')
        if 'torrent' in name: new_tags.append('torrent')
        
        new_tags_set = set(new_tags)
        
        # Determine price based on rules
        final_price = s_dict.get('price', 0)
        
        matched_rules = []
        for rule in rules:
            if rule['tags'].issubset(new_tags_set) and rule.get('duration_days', 0) == plan_days:
                matched_rules.append(rule)
                
        if matched_rules:
            # Most specific tags match wins
            best_rule = max(matched_rules, key=lambda r: len(r['tags']))
            final_price = best_rule['price']
            
        # Update server in DB
        db.collection('servers').document(s_id).update({
            'tags': new_tags,
            'price': final_price
        })
        updated_count += 1
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success', 'updated': updated_count})
    flash(f'تم تحديث {updated_count} سيرفرات بنجاح.', 'success')
    return redirect(url_for('admin_dashboard'))
"""

if "@app.route('/api/admin/rescan_servers'" not in content:
    target_str = "@app.route('/api/admin/debts_sync')"
    content = content.replace(target_str, api_code + "\n\n" + target_str)

# 4. Modify import_servers to drop old pricing_rules logic
import_servers_old = """
    pricing_rules = []
    for t_str, p_str in zip(rule_tags, rule_prices):
        if t_str and p_str:
            tags_set = set(tag.strip().lower() for tag in t_str.split(',') if tag.strip())
            if tags_set:
                pricing_rules.append({'tags': tags_set, 'price': p_str.strip()})
"""
import_servers_new = """
    pricing_rules = []
    with pricing_rules_cache_lock:
        for r_id, r_dict in pricing_rules_cache.items():
            r = r_dict.copy()
            r['tags'] = set(r.get('tags', []))
            pricing_rules.append(r)
"""
if import_servers_old in content:
    content = content.replace(import_servers_old, import_servers_new)

# Also need to add duration matching to import_servers
match_old = """
            matched_rules = []
            for rule in pricing_rules:
                if rule['tags'].issubset(keywords_lower):
                    matched_rules.append(rule)
"""
match_new = """
            matched_rules = []
            for rule in pricing_rules:
                if rule['tags'].issubset(keywords_lower) and rule.get('duration_days', 0) == plan_days:
                    matched_rules.append(rule)
"""
if match_old in content:
    content = content.replace(match_old, match_new)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Pricing rules backend applied successfully.")
