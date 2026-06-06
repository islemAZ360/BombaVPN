route_code = """
@admin_bp.route('/admin/receipt/<request_id>')
@login_required
def view_receipt(request_id):
    if not getattr(request, 'is_admin', False):
        return "Unauthorized", 403
        
    try:
        from supabase_client import supabase_admin
        req_resp = supabase_admin.table('purchase_requests').select('receipt_url').eq('id', request_id).execute()
        if not req_resp.data:
            return "Receipt not found", 404
            
        receipt_url = req_resp.data[0].get('receipt_url')
        if not receipt_url:
            return "No receipt attached", 404
            
        if receipt_url.startswith('tg:'):
            file_id = receipt_url[3:]
            import os
            import requests
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                return "Telegram bot token not configured", 500
                
            # Get file path from Telegram
            get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
            file_resp = requests.get(get_file_url).json()
            if not file_resp.get('ok'):
                return "Failed to fetch receipt from Telegram", 500
                
            file_path = file_resp['result']['file_path']
            download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            from flask import redirect
            return redirect(download_url)
        else:
            # Local file
            from flask import url_for, redirect
            return redirect(url_for('static', filename='uploads/' + receipt_url))
            
    except Exception as e:
        print("Error fetching receipt:", e)
        return "Internal Server Error", 500
"""

with open('routes/admin_routes.py', 'a', encoding='utf-8') as f:
    f.write(route_code)

print("Route appended.")
