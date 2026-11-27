import base64
import fitz
import io
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

pdf = fitz.open()
for marker in ['ID210_PAGE_A', 'ID210_PAGE_B', 'ID210_PAGE_C']:
    page = pdf.new_page()
    page.insert_text((50, 70), marker)
pdf_bytes = pdf.tobytes()
pdf.close()
errors = []
checks = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for i, viewport in enumerate(({'width': 1366, 'height': 900}, {'width': 390, 'height': 844}), 1):
        page = browser.new_page(viewport=viewport)
        page.set_default_timeout(12000)
        page.set_default_navigation_timeout(15000)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.goto('http://127.0.0.1:8767/merge-pdf', wait_until='domcontentloaded')
        studio_nav = '#tab-studio-view' if viewport['width'] > 600 else '#mob-nav-studio'
        page.wait_for_function('selector => { const e=document.querySelector(selector); return e && e.checkVisibility(); }', arg=studio_nav)
        page.locator(studio_nav).click()
        page.locator('#studio-file-input').set_input_files({'name': f'id210-{i}.pdf', 'mimeType': 'application/pdf', 'buffer': pdf_bytes})
        page.wait_for_function("() => document.querySelector('#studio-page-count')?.textContent.trim() === '3'")
        page.locator('#btn-mode-organize').wait_for(state='visible')
        page.locator('#btn-mode-organize').click()
        page.locator('.organizer-thumb-card[data-page="2"] .thumb-checkbox-label').click()
        page.wait_for_function("() => { const e=document.querySelector('#organizer-batch-bar'); return e && !e.hidden && e.getBoundingClientRect().height > 0; }")
        button = page.locator('#batch-move-up-btn')
        bounds = button.bounding_box()
        visible = bool(bounds and bounds['width'] > 0 and bounds['height'] > 0)
        with page.expect_response(lambda response: '/api/studio/pages/reorder' in response.url, timeout=15000) as event:
            button.click()
        response = event.value
        page.wait_for_function("() => window.state?.studio && !window.state.studio.isLoading && window.state.studio.totalCount === 3", timeout=60000)
        current = page.evaluate("""async () => ({name:window.state.studio.srcFile?.name,size:window.state.studio.srcFile?.size,data:window.state.studio.srcFile ? btoa(String.fromCharCode(...new Uint8Array(await window.state.studio.srcFile.arrayBuffer()))) : null,count:window.state.studio.totalCount})""")
        result_pdf = PdfReader(io.BytesIO(base64.b64decode(current['data']))) if current['data'] else None
        extracted = [item.extract_text() or '' for item in result_pdf.pages] if result_pdf else []
        markers = [next((marker for marker in ['ID210_PAGE_A','ID210_PAGE_B','ID210_PAGE_C'] if marker in text), None) for text in extracted]
        checks.append({'round':i,'viewport':viewport,'button_bounds_visible':visible,'bounds':bounds,'reorder_http_status':response.status,'downloaded_source_name':current['name'],'page_count':current['count'],'ordered_markers':markers,'content_reordered':markers==['ID210_PAGE_B','ID210_PAGE_A','ID210_PAGE_C']})
        page.close()
    browser.close()
result = {'candidate':'app.js v191 / styles.css v71', 'item':210, 'checks':checks, 'browser_errors':errors, 'passed':len(checks)==2 and all(item['button_bounds_visible'] and item['reorder_http_status']==200 and item['content_reordered'] for item in checks) and not errors}
Path('reports/launch-audit-v24/browser-id210-studio-reorder-buttons.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))