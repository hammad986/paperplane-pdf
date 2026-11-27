from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path.cwd()
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':1366,'height':900}); errors=[]; failed=[]
 page.on('pageerror',lambda e:errors.append(str(e))); page.on('requestfailed',lambda r:failed.append({'url':r.url,'error':r.failure}))
 page.goto('http://127.0.0.1:8774/html-to-pdf',wait_until='domcontentloaded',timeout=30000); page.wait_for_timeout(1200)
 fields={'url_input':page.locator('#url').count(),'copy':page.locator('body').inner_text()[:1200]}
 page.locator('#url').fill('http://127.0.0.1:8774/admin')
 page.locator('#run-button').click(); page.wait_for_function("!document.querySelector('#result').hidden",timeout=45000); page.wait_for_timeout(300)
 result={'route':page.url,'fields':fields,'title':page.locator('#result-title').inner_text(),'meta':page.locator('#result-meta').inner_text(),'download_hidden':page.locator('#result-download-link').evaluate('(e)=>e.hidden'),'errors':errors,'failed':failed}
 page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id254-private-url.png'),full_page=True)
 (root/'reports/launch-audit-v24/browser-id254-private-url.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));b.close()
