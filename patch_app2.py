import re

with open('app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Remove remaining dynv6 and dns_manager occurrences
code = re.sub(r'from dns_manager import delete_dns_record\n?', '', code)
code = re.sub(r'[ \t]*, DYNV6_TOKEN\)\n?', '\n', code)
code = re.sub(r'# Configuration for Dynv6\n?', '', code)
code = re.sub(r'# Unique subdomain per subscription: prefix-serverid\.dynv6\.net\n?', '', code)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Remaining Dynv6 code removed")
