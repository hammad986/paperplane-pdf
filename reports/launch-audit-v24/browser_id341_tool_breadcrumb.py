import json
from pathlib import Path
from playwright.sync_api import sync_playwright
rows=[];errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for w in [901,1024,1366]:
  page=b.new_page(viewport={'width':w,'height':800});page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8774/translate-pdf',wait_until='domcontentloaded')
  rows.append(page.evaluate('''()=>{const e=document.querySelector('.breadcrumb-trail');const r=e.getBoundingClientRect();return {width:innerWidth,display:getComputedStyle(e).display,crumb:e.innerText.replace(/\\s+/g,' ').trim(),boxWidth:Math.round(r.width),children:[...e.children].map(n=>({text:n.innerText.trim(),width:Math.round(n.getBoundingClientRect().width)})),docWidth:document.documentElement.scrollWidth}}'''))
  page.close()
 b.close()
result={'route':'/translate-pdf','checks':rows,'pageErrors':errors};Path('reports/launch-audit-v24/browser-id341-v203-tool-breadcrumb.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if errors or any(r['display']=='none' or r['docWidth']!=r['width'] or any(not c['width'] for c in r['children']) for r in rows):raise SystemExit(1)
