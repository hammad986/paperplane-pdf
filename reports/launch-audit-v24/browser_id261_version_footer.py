from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path.cwd(); results=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for width,height in [(320,740),(390,844),(1366,900)]:
  page=b.new_page(viewport={'width':width,'height':height}); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8774/',wait_until='domcontentloaded',timeout=30000); page.locator('#app-version').scroll_into_view_if_needed();page.wait_for_timeout(150)
  item=page.locator('#app-version')
  results.append({'viewport':width,'version_text':item.inner_text(),'visible':item.is_visible(),'display':item.evaluate('(e)=>getComputedStyle(e).display'),'visibility':item.evaluate('(e)=>getComputedStyle(e).visibility'),'rect':item.bounding_box(),'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth'),'errors':errors})
  if width==1366: page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id261-version-footer.png'),full_page=True)
  page.close()
 b.close()
(root/'reports/launch-audit-v24/browser-id261-version-footer.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
