from playwright.sync_api import sync_playwright
import json
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page()
 page.goto('http://127.0.0.1:8774/studio',wait_until='domcontentloaded')
 page.wait_for_timeout(3000)
 out={'url':page.url,'title':page.title(),'status':None,'text':page.locator('body').inner_text()[:5000],'inputs':page.locator('input[type=file]').evaluate_all('(xs)=>xs.map(x=>({id:x.id,hidden:x.hidden,accept:x.accept,outer:x.outerHTML.slice(0,300)}))'),'errors':[]}
 page.screenshot(path='reports/launch-audit-v24/debug-studio.png',full_page=True)
 print(json.dumps(out,indent=2))
 b.close()
