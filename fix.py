with open('patch_admin_js.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
with open('patch_admin_js.py', 'w', encoding='utf-8') as f:
    for line in lines:
        if "python patch_admin_js.py" not in line and "EOF" not in line:
            f.write(line)
