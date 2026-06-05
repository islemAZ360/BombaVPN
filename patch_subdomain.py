import re

with open('app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace any lingering "subdomain" references that might cause NameError
code = code.replace("if old_subdomain != subdomain or data.get('server_id') != server_id:", "if data.get('server_id') != server_id:")
code = code.replace("'allocated_subdomain': subdomain,", "'allocated_subdomain': None,")
code = code.replace("subdomain = None\n", "")
code = code.replace("subdomain = sub_data.get('allocated_subdomain')", "subdomain = None")
code = code.replace("if subdomain:\n", "if False:\n")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Subdomain NameErrors fixed")
