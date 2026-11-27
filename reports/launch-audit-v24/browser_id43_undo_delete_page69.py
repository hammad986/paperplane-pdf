import json
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright
src=Path('reports/launch-audit-v24/id2-docker-v188-69page.pdf').resolve()
out=Path('reports/launch-audit-v24/browser-id43-v203-undo-delete-page69.json')
with fitz.open(src) as d: input_pages=len(d)
errors=[]; console=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':1366,'height':900})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
 page.goto('http://127.0.0.1:8774/',wait_until='domcontentloaded'); page.locator('#tab-studio-view').click()
 page.locator('#studio-file-input').set_input_files(str(src))
 page.wait_for_function('window.state?.studio?.pdfDoc != null',timeout=30000)
 page.locator('#btn-mode-organize').click()
 page.locator('.organizer-thumb-card[data-page="69"] .thumb-checkbox').check(force=True)
 page.locator('#batch-delete-btn').click()
 page.locator('.app-confirm-dialog .app-confirm-accept').click(timeout=10000)
 page.wait_for_function('window.state.studio.pdfDoc?.numPages === 68',timeout=60000)
 banner=page.locator('#studio-undo-banner')
 banner.wait_for(state='visible',timeout=10000)
 before={'pageCount':page.evaluate('window.state.studio.pdfDoc.numPages'),'banner':banner.inner_text(),'undoButton':banner.locator('button').inner_text()}
 page.wait_for_timeout(11000)
 before['stillVisibleAfter11Seconds']=banner.is_visible()
 banner.locator('button').click()
 page.wait_for_function('window.state.studio.pdfDoc?.numPages === 69',timeout=30000)
 result={'inputPages':input_pages,'afterDelete':before,'afterUndoPages':page.evaluate('window.state.studio.pdfDoc.numPages'),'pageErrors':errors,'consoleErrors':console}
 b.close()
out.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
if input_pages!=69 or before['pageCount']!=68 or not before['stillVisibleAfter11Seconds'] or result['afterUndoPages']!=69 or errors: raise SystemExit(1)
