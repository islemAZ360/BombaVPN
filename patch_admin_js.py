import re

with open('templates/admin_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

sync_js = """
    // --- Real-time Auto-refresh for All Dashboard Data ---
    async function fetchDashboardSync() {
        try {
            const resp = await fetch('/api/admin/dashboard_sync');
            if (!resp.ok) return;
            const data = await resp.json();
            
            // 1. Update Server Statistics HUD
            if(data.server_stats) {
                const hudBoxes = document.querySelectorAll('.hud-stat-box .hud-stat-number');
                if(hudBoxes.length >= 5) {
                    hudBoxes[0].innerText = data.server_stats.total;
                    hudBoxes[1].innerText = data.server_stats.gemini;
                    hudBoxes[2].innerText = data.server_stats.yt;
                    hudBoxes[3].innerText = data.server_stats.lte;
                    hudBoxes[4].innerText = data.server_stats.ru;
                    if(hudBoxes[5]) hudBoxes[5].innerText = data.server_stats.torrent;
                }
            }
            
            // 2. Update Active Users Table
            const activeTbody = document.getElementById('active-users-tbody');
            if(activeTbody && data.active_users) {
                let html = '';
                data.active_users.forEach(u => {
                    let ips = u.accessed_ips ? u.accessed_ips.length : 0;
                    let devices = u.accessed_devices ? u.accessed_devices.length : 0;
                    html += `<tr>
                        <td>
                            <div style="font-weight: 500; color: #fff; max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px;" title="${u.email}">
                                ${u.email}
                                ${u.email === 'islamazaizia360@gmail.com' ? '<span style="background:var(--primary); color:#000; font-size:0.65rem; padding:2px 6px; border-radius:4px; font-weight:bold;">Admin</span>' : ''}
                            </div>
                            <div style="margin-top: 5px; font-size: 0.8rem; color: #aaa;">
                                <span>🌐 ${ips} IPs</span> | <span>📱 ${devices} Devices</span>
                            </div>
                            <div style="margin-top: 10px; display: flex; gap: 5px;">
                                <button type="button" class="icon-btn assign-btn" onclick="openAssignModal('${u.id}', '')" title="Assign New Server" style="padding: 4px;">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"></path></svg>
                                </button>
                                <button type="button" class="icon-btn msg-btn" onclick="openMessageModal('${u.id}', '${u.email}')" title="Send Message" style="padding: 4px;">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                                <form method="POST" action="/admin/delete_user/${u.id}" onsubmit="return confirm('هل أنت متأكد من حذف هذا المستخدم وجميع اشتراكاته؟');" style="display:inline;">
                                    <button type="submit" class="icon-btn reject-btn" title="Delete User" style="padding: 4px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"></path></svg>
                                    </button>
                                </form>
                            </div>
                        </td>
                        <td>`;
                    u.subscriptions.forEach(sub => {
                        let badgeColor = sub.status === 'active' ? '#4CAF50' : '#F44336';
                        html += `
                            <div style="background: rgba(255,255,255,0.03); padding: 8px; border-radius: 6px; margin-bottom: 8px; border: 1px solid rgba(255,255,255,0.05);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                                    <span style="font-weight: 500; color: #fff;">${sub.allocated_server_name || 'N/A'}</span>
                                    <span style="font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; background: ${badgeColor}20; color: ${badgeColor}; border: 1px solid ${badgeColor}40;">${sub.status.toUpperCase()}</span>
                                </div>
                                <div style="font-size: 0.8rem; color: #aaa;">
                                    <div style="margin-bottom: 3px;">Start: ${sub.created_at ? new Date(sub.created_at).toLocaleString() : 'N/A'}</div>
                                    <div>Exp: ${sub.expires_at ? new Date(sub.expires_at).toLocaleString() : 'N/A'}</div>
                                </div>
                            </div>
                        `;
                    });
                    if (u.subscriptions.length === 0) {
                        html += `<span style="color: #aaa; font-style: italic;">No active subs</span>`;
                    }
                    html += `</td></tr>`;
                });
                if(data.active_users.length === 0) html = '<tr><td colspan="2" style="text-align: center; color: #aaa;">No active users found.</td></tr>';
                activeTbody.innerHTML = html;
            }

            // 3. Update All Users Table
            const allTbody = document.getElementById('all-users-tbody');
            if(allTbody && data.all_users) {
                let html = '';
                data.all_users.forEach(u => {
                    let ips = u.accessed_ips ? u.accessed_ips.length : 0;
                    let devices = u.accessed_devices ? u.accessed_devices.length : 0;
                    let statusBadge = u.status === 'active' ? '<span style="color:#4CAF50; background:rgba(76,175,80,0.1); padding:2px 6px; border-radius:4px; font-size:0.75rem;">Active</span>' : 
                                      (u.status === 'expired' ? '<span style="color:#F44336; background:rgba(244,67,54,0.1); padding:2px 6px; border-radius:4px; font-size:0.75rem;">Expired</span>' : 
                                      '<span style="color:#FF9800; background:rgba(255,152,0,0.1); padding:2px 6px; border-radius:4px; font-size:0.75rem;">No Sub</span>');
                    
                    html += `<tr>
                        <td>
                            <div style="font-weight: 500; color: #fff; max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px;" title="${u.email}">
                                ${u.email}
                                ${u.email === 'islamazaizia360@gmail.com' ? '<span style="background:var(--primary); color:#000; font-size:0.65rem; padding:2px 6px; border-radius:4px; font-weight:bold;">Admin</span>' : ''}
                            </div>
                            <div style="margin-top: 5px; font-size: 0.8rem; color: #aaa;">
                                <span>🌐 ${ips} IPs</span> | <span>📱 ${devices} Devices</span>
                            </div>
                            <div style="margin-top: 10px; display: flex; gap: 5px;">
                                <button type="button" class="icon-btn assign-btn" onclick="openAssignModal('${u.id}', '')" title="Assign New Server" style="padding: 4px;">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"></path></svg>
                                </button>
                                <button type="button" class="icon-btn msg-btn" onclick="openMessageModal('${u.id}', '${u.email}')" title="Send Message" style="padding: 4px;">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                                <form method="POST" action="/admin/delete_user/${u.id}" onsubmit="return confirm('هل أنت متأكد من حذف هذا المستخدم وجميع اشتراكاته؟');" style="display:inline;">
                                    <button type="submit" class="icon-btn reject-btn" title="Delete User" style="padding: 4px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"></path></svg>
                                    </button>
                                </form>
                            </div>
                        </td>
                        <td style="vertical-align: middle;">${statusBadge}</td>
                        <td style="vertical-align: middle; color: #aaa;">${u.created_at ? new Date(u.created_at).toLocaleString() : 'N/A'}</td>
                    </tr>`;
                });
                if(data.all_users.length === 0) html = '<tr><td colspan="3" style="text-align: center; color: #aaa;">No users found.</td></tr>';
                allTbody.innerHTML = html;
            }

            // 4. Update Servers Table
            const serversTbody = document.getElementById('servers-tbody');
            if(serversTbody && data.servers) {
                let html = '';
                data.servers.forEach(s => {
                    let countryCode = s.country_code ? s.country_code : 'xx';
                    let isExpired = s.expires_at ? new Date(s.expires_at) < new Date() : true;
                    let expStr = s.expires_at ? new Date(s.expires_at).toLocaleString() : 'No Expire Data';
                    
                    html += `<tr ${isExpired ? 'style="opacity: 0.6; background: rgba(244,67,54,0.05);"' : ''}>
                        <td>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <img src="https://flagcdn.com/24x18/${countryCode}.png" alt="flag" style="border-radius: 2px;">
                                <span style="font-weight: 500; color: #fff;">${s.name}</span>
                            </div>
                            <div style="margin-top: 5px; font-size: 0.8rem; color: #aaa;">IP: ${s.original_ip}</div>
                        </td>
                        <td style="vertical-align: middle; color: #aaa;">${s.price || 'N/A'} DZD</td>
                        <td style="vertical-align: middle;">
                            <div style="${isExpired ? 'color: #F44336;' : 'color: #4CAF50;'}">
                                ${expStr}
                                ${isExpired ? '<span style="margin-left: 8px; font-size: 0.7rem; background: #F44336; color: #fff; padding: 2px 6px; border-radius: 4px;">Expired</span>' : ''}
                            </div>
                        </td>
                    </tr>`;
                });
                if(data.servers.length === 0) html = '<tr><td colspan="3" style="text-align: center; color: #aaa;">No servers found.</td></tr>';
                serversTbody.innerHTML = html;
            }

            // 5. Update Tickets Table
            const ticketsTbody = document.getElementById('tickets-tbody');
            if(ticketsTbody && data.tickets) {
                let html = '';
                data.tickets.forEach(msg => {
                    html += `<tr>
                        <td>
                            <div style="font-weight: 500; color: #fff;">${msg.user_email || 'Unknown User'}</div>
                            <div style="font-size: 0.8rem; color: #aaa; margin-top: 3px;">${msg.created_at ? new Date(msg.created_at).toLocaleString() : ''}</div>
                        </td>
                        <td>
                            <div style="white-space: pre-wrap; font-size: 0.9rem; color: #ddd; background: rgba(255,255,255,0.03); padding: 10px; border-radius: 6px;">${msg.text}</div>
                        </td>
                        <td style="vertical-align: middle;">
                            <form method="POST" action="/admin/delete_message/${msg.id}" onsubmit="return confirm('Delete message?');">
                                <button type="submit" class="btn btn-hollow-danger btn-small">Delete</button>
                            </form>
                        </td>
                    </tr>`;
                });
                if(data.tickets.length === 0) html = '<tr><td colspan="3" style="text-align: center; color: #aaa;">No support tickets.</td></tr>';
                ticketsTbody.innerHTML = html;
            }

        } catch(e) {
            console.error('Failed to sync dashboard data:', e);
        }
    }
    
    // Poll every 5 seconds
    setInterval(fetchDashboardSync, 5000);
"""

if "fetchDashboardSync" not in content:
    target_str = "setInterval(fetchPendingRequests, 3000);"
    content = content.replace(target_str, target_str + "\n" + sync_js)
    with open('templates/admin_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("JS patched in admin_dashboard.")
else:
    print("Already patched.")
