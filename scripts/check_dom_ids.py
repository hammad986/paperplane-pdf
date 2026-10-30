import re

with open("web/index.html", "r", encoding="utf-8") as f:
    html = f.read()

ids_in_html = set(re.findall(r'id=["\']([a-zA-Z0-9_\-]+)["\']', html))

with open("web/assets/app.js", "r", encoding="utf-8") as f:
    js = f.read()

js_ids = set(re.findall(r"\$\(['\"]#([a-zA-Z0-9_\-]+)['\"]\)", js))

missing = []
for jid in js_ids:
    if jid not in ids_in_html:
        missing.append(jid)

print(f"Total IDs checked in app.js: {len(js_ids)}")
print(f"IDs in app.js not found in index.html: {len(missing)}")
for m in sorted(missing):
    lines = [line.strip() for line in js.splitlines() if f"#{m}" in line]
    print(f"  #{m}:")
    for l in lines[:2]:
        print(f"     {l[:100]}")
