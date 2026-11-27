from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path.cwd(); rows=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for w in (320,390):
  page=b.new_page(viewport={'width':w,'height':844}); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8774/jpg-to-pdf',wait_until='domcontentloaded');page.wait_for_timeout(200)
  body=page.locator('body').inner_text(); selects=page.locator('#page_size, #orientation, #fit_mode').evaluate_all('(xs)=>xs.map(e=>({id:e.id,value:e.value,options:[...e.options].map(o=>o.textContent)}))')
  rows.append({'width':w,'legacy_paper_size_claims':[t for t in ['A4, Letter, or auto paper sizes','A4 or Letter size auto'] if t.lower() in body.lower()],'copy':body[body.find('JPG'):body.find('Encrypted')+40] if 'JPG' in body else body[:700],'controls':selects,'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth'),'errors':errors})
  if w==390: page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id264-jpg-copy-390.png'),full_page=True)
  page.close()
 b.close()
(root/'reports/launch-audit-v24/browser-id264-jpg-copy.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
