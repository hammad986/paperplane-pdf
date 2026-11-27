import base64, json, os
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright
out = Path('reports/launch-audit-v24/browser-id319-v203-compress-warning.json')
out.parent.mkdir(parents=True, exist_ok=True)
src = Path('reports/launch-audit-v24/id319-input.pdf')
with fitz.open() as d:
    p=d.new_page(); p.insert_text((72,72),'ID319 ORIGINAL MARKER')
    d.save(src)
result_pdf=Path('reports/launch-audit-v24/id319-output.pdf')
with fitz.open() as d:
    p=d.new_page(); p.insert_text((72,72),'ID319 COMPRESSED OUTPUT MARKER')
    d.save(result_pdf)
errors=[]; console=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1920,'height':1080}, accept_downloads=True)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: console.append(m.text) if m.type=='error' else None)
    page.route('**/api/studio/compress', lambda route: route.fulfill(status=200, body=result_pdf.read_bytes(), content_type='application/pdf', headers={'X-Original-Size':'3500000','X-Output-Size':'1832960','X-Saved-Bytes':'1667040','X-Percent-Saved':'47.6','X-Preset-Used':'100kb','X-Target-Achieved':'false','X-Compression-Note':'Compressed to 1,790.0 KB; the requested target could not be reached while preserving document content.'}))
    page.goto('http://127.0.0.1:8774/', wait_until='domcontentloaded')
    page.wait_for_function("window.state != null", timeout=15000)
    page.locator('#tab-studio-view').click()
    page.locator('#studio-file-input').set_input_files(str(src.resolve()))
    page.wait_for_function("window.state?.studio?.pdfDoc != null", timeout=15000)
    pdf_b64=base64.b64encode(src.read_bytes()).decode('ascii')
    page.evaluate("b64 => window.PaperplaneOptimization.openCompressModal(new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'input.pdf', {type:'application/pdf'}))", pdf_b64)
    page.wait_for_function("!document.querySelector('#compress-modal').hidden", timeout=10000)
    page.locator('#compress-target-size').fill('100')
    page.locator('#compress-target-unit').select_option('KB')
    page.locator('#btn-apply-compress').click()
    page.wait_for_function("document.querySelector('.toast-notice')?.textContent.includes('1,790.0 KB')", timeout=30000)
    toast=page.locator('.toast-notice').last.inner_text()
    cls=page.locator('.toast-notice').last.get_attribute('class')
    output={'url':page.url,'toast':toast,'toastClass':cls,'modalHidden':page.locator('#compress-modal').evaluate('(e)=>e.hidden'),'errors':errors,'consoleErrors':console}
    browser.close()
out.write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps(output,indent=2))
if errors or '1,790.0 KB' not in toast or 'warning' not in (cls or ''): raise SystemExit(1)
