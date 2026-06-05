import re

with open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove old Pricing Rules from import form
# Find the div that contains pricing rules (around lines 148-159)
old_rules_str = """        <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <label style="font-size: 0.85rem; color: #a0a0a0; margin: 0;">Pricing Rules</label>
                <button type="button" class="btn btn-primary btn-small" onclick="addPricingRule()">+ Add Rule</button>
            </div>
            <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                <input type="text" name="price_base" class="form-control" placeholder="Base Price (Default)" style="flex: 1;">
            </div>
            <div id="pricing-rules-container" style="display: flex; flex-direction: column; gap: 10px;">
                <!-- Rules will be injected here -->
            </div>
        </div>"""
content = content.replace(old_rules_str, "")

# 2. Add Pricing Rules Card
pricing_rules_card = """
<div class="card" style="margin-bottom: 20px;">
    <h3 style="display: flex; align-items: center; justify-content: space-between;">
        <span>Pricing Rules System</span>
    </h3>
    <p style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1rem;">Create rules based on tags and durations.</p>
    
    <div style="display: grid; grid-template-columns: 1fr; gap: 15px; margin-bottom: 20px;" id="saved-pricing-rules">
        <!-- Fetched rules will be injected here by AJAX -->
    </div>
    
    <form method="POST" action="/api/admin/pricing_rules" style="display: flex; gap: 10px; align-items: flex-end; background: rgba(255,255,255,0.03); padding: 15px; border-radius: 8px; border: 1px dashed rgba(255,255,255,0.1);">
        <div style="flex: 2;">
            <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 5px;">Tags (Comma separated)</label>
            <input type="text" name="tags" class="form-control" placeholder="e.g. torrent, ru" required>
        </div>
        <div style="flex: 1;">
            <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 5px;">Duration (Days)</label>
            <input type="number" name="duration_days" class="form-control" placeholder="e.g. 30" required>
        </div>
        <div style="flex: 1;">
            <label style="font-size: 0.85rem; color: var(--text-muted); display: block; margin-bottom: 5px;">Price</label>
            <input type="number" name="price" class="form-control" placeholder="e.g. 500" required>
        </div>
        <div>
            <button type="submit" class="btn btn-primary">+ Add</button>
        </div>
    </form>
</div>
"""

# Insert pricing rules card before Server Statistics
stats_header = '<h4 style="margin-bottom: 1rem; color: var(--primary);">Server Statistics</h4>'
if stats_header in content and 'Pricing Rules System' not in content:
    content = content.replace('<div class="card">\n    ' + stats_header, pricing_rules_card + '\n<div class="card">\n    ' + stats_header)

# 3. Add Re-Scan Button
servers_header = """    <h3 style="display: flex; align-items: center; justify-content: space-between;">
        <span>{{ _('Servers') }}</span>
"""
servers_rescan_btn = """        <form method="POST" action="/api/admin/rescan_servers" onsubmit="return confirm('هل أنت متأكد من إعادة فحص جميع السيرفرات؟ سيتم تحديث الأسعار والوسوم.');">
            <button type="submit" class="btn btn-primary btn-small">إعادة فحص السيرفرات (Re-Scan)</button>
        </form>
"""
if servers_header in content and 'rescan_servers' not in content:
    content = content.replace(servers_header, servers_header + servers_rescan_btn)

# 4. Add JS to fetch and display pricing rules
fetch_rules_js = """
    async function fetchPricingRules() {
        try {
            const resp = await fetch('/api/admin/pricing_rules');
            if (!resp.ok) return;
            const data = await resp.json();
            const container = document.getElementById('saved-pricing-rules');
            if(!container) return;
            
            let html = '';
            data.rules.forEach(r => {
                let tagsHtml = '';
                if(r.tags && r.tags.length > 0) {
                    r.tags.forEach(t => {
                        tagsHtml += `<span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; color: #fff;">${t}</span>`;
                    });
                } else {
                    tagsHtml = `<span style="color: #aaa; font-style: italic;">No Tags</span>`;
                }
                
                html += `
                <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2); padding: 10px 15px; border-radius: 8px; border-left: 3px solid var(--primary);">
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <div style="display: flex; gap: 5px;">${tagsHtml}</div>
                        <div style="color: #aaa; font-size: 0.85rem;">⏳ ${r.duration_days} Days</div>
                        <div style="font-weight: bold; color: #4CAF50;">💰 ${r.price} DZD</div>
                    </div>
                    <form method="POST" action="/api/admin/pricing_rules/${r.id}/delete" onsubmit="return confirm('Delete this rule?');" style="margin:0;">
                        <button type="submit" class="icon-btn reject-btn" title="Delete Rule">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                    </form>
                </div>`;
            });
            if(data.rules.length === 0) {
                html = '<div style="color: #aaa; text-align: center;">No pricing rules defined. Add one below.</div>';
            }
            container.innerHTML = html;
        } catch(e) { console.error('Failed to fetch rules', e); }
    }
    
    // Fetch rules on load
    document.addEventListener('DOMContentLoaded', fetchPricingRules);
    // Also fetch every 10 seconds just in case
    setInterval(fetchPricingRules, 10000);
"""

if 'fetchPricingRules' not in content:
    content = content.replace("async function fetchDashboardSync()", fetch_rules_js + "\n    async function fetchDashboardSync()")

# 5. Remove the old addPricingRule JS
old_js_func_pattern = re.compile(r'function addPricingRule\(\) \{.*?\n    \}\n', re.DOTALL)
content = re.sub(old_js_func_pattern, '', content)

with open('templates/admin_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("admin_dashboard.html patched successfully.")
