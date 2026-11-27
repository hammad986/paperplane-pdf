from pathlib import Path
import json
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8501'; OUT=Path('reports/launch-audit-v23'); SOURCE=OUT/'fixtures/deutschebahn-2025-annual-report-excerpt-12p.pdf'
results=[]
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True)
 for round_no in (1,2):
  page=b.new_page(accept_downloads=True); errors=[]; posts=[]; downloads=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('request',lambda r:posts.append(r.url) if '/api/jobs' in r.url and r.method=='POST' else None)
  page.on('download',lambda d:downloads.append(d.suggested_filename))
  response=page.goto(BASE+'/pdf-to-word',wait_until='domcontentloaded'); assert response and response.status==200
  page.locator('#file-input').set_input_files(str(SOURCE)); page.locator('#run-button').click()
  dialog=page.locator('dialog.app-confirm-dialog'); dialog.wait_for(state='visible',timeout=30000)
  message=dialog.locator('p').inner_text(); assert 'custom-font glyphs' in message or 'math' in message or 'selectable text' in message,message
  assert 'Upload and retry' in dialog.inner_text()
  dialog.locator('.app-confirm-cancel').click(); page.wait_for_function("!document.querySelector('dialog.app-confirm-dialog')")
  page.wait_for_function("document.querySelector('#result')?.hidden === false",timeout=10000)
  result={'round':round_no,'dialog_reason':message,'cancelled':True,'job_posts':posts,'downloads':downloads,'page_errors':errors,'local_app_asset':page.locator('script[src*="app.js"]').get_attribute('src')}
  assert not posts and not downloads and not errors,result
  results.append(result); page.close()
 b.close()
out={'source':SOURCE.name,'pages':12,'rounds':results}
(OUT/'browser-id37-local-pdf-to-word-real-fallback.json').write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2))
