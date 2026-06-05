import re

with open('templates/debts.html', 'r', encoding='utf-8') as f:
    content = f.read()

debts_js = """
<script>
    async function fetchDebtsSync() {
        try {
            const resp = await fetch('/api/admin/debts_sync');
            if (!resp.ok) return;
            const data = await resp.json();
            
            const tbody = document.getElementById('debts-tbody');
            if (!tbody) return;
            
            let html = '';
            data.debts.forEach(debt => {
                const tr = document.createElement('tr');
                let rowHtml = `
                    <td>
                        <div style="font-weight: 500; color: #fff;">${debt.email}</div>
                    </td>
                    <td style="color: #aaa;">${debt.server_name}</td>
                    <td>
                        <span style="color: #F44336; font-weight: bold;">
                            ${debt.debt_days}d ${debt.debt_hours}h
                        </span>
                    </td>
                    <td style="color: #aaa;">
                        <div style="font-size: 0.85rem; margin-bottom: 4px;">Server: ${new Date(debt.server_expires_at).toLocaleString()}</div>
                        <div style="font-size: 0.85rem;">User: ${new Date(debt.subscription_expires_at).toLocaleString()}</div>
                    </td>
                    <td>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn btn-hollow-primary btn-small" onclick="openMessageModal('${debt.id}', '${debt.email}')">Message</button>
                            <form method="POST" action="/admin/delete_user/${debt.id}" onsubmit="return confirm('Delete this user?');" style="margin: 0;">
                                <button type="submit" class="btn btn-hollow-danger btn-small">Delete User</button>
                            </form>
                        </div>
                    </td>
                `;
                html += `<tr>${rowHtml}</tr>`;
            });
            
            if(data.debts.length === 0) {
                html = '<tr><td colspan="5" style="text-align: center; color: #aaa; padding: 2rem;">{{ _("NoDebts") }}</td></tr>';
            }
            
            tbody.innerHTML = html;
        } catch(e) {
            console.error('Failed to sync debts:', e);
        }
    }
    
    // Poll every 5 seconds
    setInterval(fetchDebtsSync, 5000);
</script>
"""

# Insert debts_js before {% endblock %}
target_str = "{% endblock %}"
if "fetchDebtsSync" not in content and target_str in content:
    content = content.replace(target_str, debts_js + "\n" + target_str)
    
    # We must also add id="debts-tbody" to the tbody tag in debts.html
    content = content.replace("<tbody>", '<tbody id="debts-tbody">', 1)
    
    with open('templates/debts.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("debts.html patched successfully.")
else:
    print("Could not patch debts.html or already patched.")
