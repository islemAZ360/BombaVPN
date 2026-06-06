import os
import re

with open('original_app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

decorators_map = {}
current_decorators = []

for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('@'):
        current_decorators.append(line)
    elif stripped.startswith('def '):
        match = re.match(r'def\s+(\w+)\s*\(', stripped)
        if match:
            func_name = match.group(1)
            if current_decorators:
                decorators_map[func_name] = current_decorators
        current_decorators = []
    elif not stripped or stripped.startswith('#'):
        continue
    else:
        current_decorators = []

bp_map = {
    'admin_routes.py': 'admin_bp',
    'api_routes.py': 'api_bp',
    'auth_routes.py': 'auth_bp',
    'main_routes.py': 'main_bp'
}

for filename, bp_name in bp_map.items():
    filepath = os.path.join('routes', filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        file_lines = f.readlines()
        
    out_lines = []
    for line in file_lines:
        stripped = line.strip()
        if stripped.startswith('def '):
            match = re.match(r'def\s+(\w+)\s*\(', stripped)
            if match:
                func_name = match.group(1)
                if func_name in decorators_map:
                    for dec in decorators_map[func_name]:
                        dec = dec.replace('@app.route', f'@{bp_name}.route')
                        dec = dec.replace('@app.errorhandler', f'@{bp_name}.errorhandler')
                        out_lines.append(dec)
        out_lines.append(line)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)
    print(f"Fixed {filename}")
