from pathlib import Path
import json
from playwright.sync_api import sync_playwright
OUT=Path('reports/launch-audit-v23')
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True); page=b.new_page(accept_downloads=True)
 errors=[]; jobs=[]; downloads=[]
 page.on('pageerror',lambda e:errors.append(str(e))); page.on('request',lambda r:jobs.append(r.url) if '/api/jobs' in r.url and r.method=='POST' else None); page.on('download',lambda d:downloads.append(d.suggested_filename))
 page.goto('http://127.0.0.1:8501/pdf-to-word',wait_until='domcontentloaded'); page.locator('#file-input').set_input_files(str(OUT/'fixtures/id37-local-text-12-pages.pdf'))
 page.locator('#run-button').click(); page.wait_for_timeout(5000)
 d=page.locator('dialog.app-confirm-dialog'); result={'app':page.locator('script[src*="app.js"]').get_attribute('src'),'dialog':d.count(),'dialog_text':d.inner_text() if d.count() else None,'result_visible':not page.locator('#result').evaluate('(e)=>e.hidden'),'result_text':page.locator('#result').inner_text(),'downloads':downloads,'jobs':jobs,'errors':errors,'mode':page.locator('#client-mode-toggle').is_checked() if page.locator('#client-mode-toggle').count() else None}
 (OUT/'browser-id37-local-pdf-to-word-diagnostic.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2)); b.close()
