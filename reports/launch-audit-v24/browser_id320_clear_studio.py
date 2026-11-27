import json
from pathlib import Path
from playwright.sync_api import sync_playwright
src=Path('reports/launch-audit-v24/id319-input.pdf').resolve()
out=Path('reports/launch-audit-v24/browser-id320-v203-clear-studio.json')
errors=[]; console=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':1366,'height':900})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
 page.goto('http://127.0.0.1:8774/',wait_until='domcontentloaded')
 page.locator('#tab-studio-view').click()
 page.locator('#studio-file-input').set_input_files(str(src))
 page.wait_for_function('window.state?.studio?.pdfDoc != null',timeout=20000)
 page.locator('#studio-clear-pdf-btn').click()
 page.locator('.app-confirm-dialog .app-confirm-accept').click()
 page.wait_for_function('window.state?.studio?.pdfDoc == null',timeout=20000)
 page.wait_for_timeout(1000)
 result={'url':page.url,'pdfCleared':page.evaluate('window.state.studio.pdfDoc === null'),'toast':page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else None,'storageBlockMessage':page.get_by_text('Close other Paperplane tabs and try again.',exact=False).count(),'errors':errors,'consoleErrors':console}
 b.close()
out.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
if not result['pdfCleared'] or result['storageBlockMessage'] or errors: raise SystemExit(1)
