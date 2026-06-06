import glob

for path in glob.glob('**/*.py', recursive=True):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'or '0')' in content and 'request.form.get' in content:
                content = content.replace("or '0')", "or '0')")
                with open(path, 'w', encoding='utf-8') as out:
                    out.write(content)
                print('Fixed in ' + path)
    except Exception as e:
        print(e)
