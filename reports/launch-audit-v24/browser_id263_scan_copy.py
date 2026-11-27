from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path.cwd(); out=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for width in (320,390):
  page=b.new_page(viewport={'width':width,'height':844}); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8774/scan-to-pdf',wait_until='domcontentloaded');page.wait_for_timeout(250)
  body=page.locator('body').inner_text()
  row={'width':width,'has_deskew_claim':'deskew' in body.lower(),'mentions_auto_contrast':'contrast and sharpness' in body.lower(),'mentions_browser_enhancement_limit':'skips automatic contrast and sharpness enhancement' in body.lower(),'horizontal_overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth'),'errors':errors}
  out.append(row)
  if width==390: page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id263-scan-copy-390.png'),full_page=True)
  page.close()
 b.close()
(root/'reports/launch-audit-v24/browser-id263-scan-copy.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
