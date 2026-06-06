with open('translations.py', 'r', encoding='utf-8') as f:
    content = f.read()

en_translation = "'NoSourceLinks': 'No saved source links yet. Import servers from a link to show here.',"
ar_translation = "'NoSourceLinks': 'لا توجد روابط مصدر محفوظة بعد. قم باستيراد سيرفرات من رابط ليظهر هنا.',"
fr_translation = "'NoSourceLinks': 'Aucun lien source enregistré pour l\\'instant. Importez des serveurs depuis un lien pour les afficher ici.',"

# Replace the first opening brace after 'en': {
content = content.replace("'en': {", f"'en': {{\\n        {en_translation}")
content = content.replace("'ar': {", f"'ar': {{\\n        {ar_translation}")
content = content.replace("'fr': {", f"'fr': {{\\n        {fr_translation}")

with open('translations.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Translations updated.")
