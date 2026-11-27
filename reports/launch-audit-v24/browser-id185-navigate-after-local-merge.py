import fitz,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
pdf=fitz.open()
for i in range(12):
 page=pdf.new_page();page.insert_text((50,70),f'ID185 PAGE {i+1}')
buf=pdf.tobytes();pdf.close();errs=[];rows=[]
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page();page.set_default_timeout(20000);page.set_default_navigation_timeout(20000);page.on('pageerror',lambda e:errs.append(str(e)));page.on('console',lambda m:errs.append(m.text) if m.type=='error' else None)
 for n in (1,2):
  page.goto('http://127.0.0.1:8767/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("()=>window.state?.operation==='merge'")
  toggle=page.locator('#client-privacy-toggle')
  if not toggle.is_checked(): page.locator('#sidebar label.toggle-switch-sm').click()
  page.locator('#file-input').set_input_files([{'name':f'id185-{n}-a.pdf','mimeType':'application/pdf','buffer':buf},{'name':f'id185-{n}-b.pdf','mimeType':'application/pdf','buffer':buf}])
  page.locator('#run-button').click();page.wait_for_function("()=>!document.querySelector('#result')?.hidden",timeout=60000)
  started=time.monotonic();response=page.goto('http://127.0.0.1:8767/split-pdf',wait_until='domcontentloaded',timeout=20000);page.wait_for_function("()=>window.state?.operation==='split'",timeout=15000);elapsed=time.monotonic()-started
  rows.append({'round':n,'result_visible':True,'navigated_to_split':response.status==200 and page.locator('#tool-title').inner_text()=='Split / extract','navigation_seconds':round(elapsed,2),'browser_document_frozen':False})
 b.close()
result={'build':'app.js v191/styles71','operation':'local Merge then navigate','pdf_pages':12,'rounds':rows,'browser_errors':errs,'passed':len(rows)==2 and all(x['result_visible'] and x['navigated_to_split'] and x['navigation_seconds']<10 for x in rows) and not errs}
Path('reports/launch-audit-v24/browser-id185-navigate-after-local-merge.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))