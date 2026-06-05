import re

with open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add Source Links Card
source_links_card = """
<div class="card" style="margin-bottom: 20px;">
    <h3 style="display: flex; align-items: center; justify-content: space-between;">
        <span>Provider Subscriptions (Source Links)</span>
    </h3>
    <p style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1rem;">These links were saved when you imported servers. Click Sync to fetch the latest servers from the link.</p>
    
    <div style="display: grid; grid-template-columns: 1fr; gap: 15px; margin-bottom: 20px;" id="saved-source-links">
        <!-- Fetched source links will be injected here by AJAX -->
    </div>
</div>
"""

# Insert source links card before Server Statistics, but after Pricing Rules if possible.
# Actually, let's put it right after the UploadJson card (Import Servers).
upload_json_end = """        <button type="submit" class="btn btn-primary" style="width: fit-content; align-self: flex-end;">{{ _('ImportServersBtn') }}</button>
    </form>
</div>"""
if upload_json_end in content and 'Provider Subscriptions' not in content:
    content = content.replace(upload_json_end, upload_json_end + '\n\n' + source_links_card)

# 2. Add AJAX JS for source links into fetchDashboardSync
ajax_js = """
            // 2.5 Update Source Links
            const linksContainer = document.getElementById('saved-source-links');
            if (linksContainer && data.source_links) {
                let html = '';
                data.source_links.forEach(l => {
                    let createdStr = l.created_at ? new Date(l.created_at).toLocaleString() : 'N/A';
                    let shortUrl = l.url;
                    if(shortUrl.length > 50) shortUrl = shortUrl.substring(0, 50) + '...';
                    
                    html += `
                    <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2); padding: 10px 15px; border-radius: 8px; border-left: 3px solid var(--accent);">
                        <div style="display: flex; flex-direction: column; gap: 5px;">
                            <div style="font-weight: bold; color: #fff;">${shortUrl}</div>
                            <div style="display: flex; gap: 15px; font-size: 0.8rem; color: #aaa;">
                                <span>🗓️ Plan: ${l.plan_days || 0}d ${l.plan_hours || 0}h ${l.plan_minutes || 0}m</span>
                                <span>🕰️ Real: ${l.real_days || 0}d ${l.real_hours || 0}h ${l.real_minutes || 0}m</span>
                            </div>
                        </div>
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <form method="POST" action="/api/admin/sync_link/${l.id}" onsubmit="return confirm('Fetch and synchronize servers from this link?');" style="margin:0;">
                                <button type="submit" class="btn btn-primary btn-small" title="Sync / Fetch Updates" style="padding: 5px 10px; font-size: 0.8rem; border-radius: 6px;">
                                    🔄 Sync
                                </button>
                            </form>
                            <form method="POST" action="/api/admin/delete_link/${l.id}" onsubmit="return confirm('Delete this saved link? (This will NOT delete the servers)');" style="margin:0;">
                                <button type="submit" class="icon-btn reject-btn" title="Delete Link">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </form>
                        </div>
                    </div>`;
                });
                if(data.source_links.length === 0) {
                    html = '<div style="color: #aaa; text-align: center;">No saved subscription links.</div>';
                }
                linksContainer.innerHTML = html;
            }
"""

if '// 2.5 Update Source Links' not in content:
    content = content.replace("// 3. Update Users Table", ajax_js + "\n\n            // 3. Update Users Table")

with open('templates/admin_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("admin_dashboard.html patched for source links successfully.")
