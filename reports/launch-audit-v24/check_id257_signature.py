from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root = Path.cwd()
pdf = root / 'reports/launch-audit-v24/id2-docker-v188-69page.pdf'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:8774/studio', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(1500)
    result={"url_before":page.url,"title":page.title(),"upload_inputs":page.locator('input[type=file]').count()}
    inp=page.locator('#studio-file-input')
    inp.set_input_files(str(pdf))
    page.wait_for_function("!!window.PaperplaneEditor?.editorState?.sourceFile", timeout=90000)
    page.wait_for_timeout(1500)
    result['editor_ready']=True
    page.locator('#btn-more-tools-trigger').click()
    page.locator('#studio-sign-btn').click()
    page.wait_for_timeout(500)
    result.update({"url_after":page.url,"digital_modal_hidden":page.locator('#digital-sign-modal').evaluate('(e)=>e.hidden'),"canvas_signature_modal_hidden":page.locator('#editor-signature-modal').evaluate('(e)=>e.hidden'),"errors":errors})
    page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id257-v203-signature-entry.png'), full_page=True)
    (root/'reports/launch-audit-v24/browser-id257-v203-signature-entry.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    browser.close()
