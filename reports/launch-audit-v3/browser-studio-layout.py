from playwright.sync_api import sync_playwright
from pathlib import Path
PDF = str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
BASE = 'http://127.0.0.1:8501'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for width,height,name in [(1440,1000,'desktop'),(375,812,'phone')]:
        page = b.new_page(viewport={'width':width,'height':height}, device_scale_factor=1)
        errors=[]
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto(BASE, wait_until='domcontentloaded', timeout=15000)
        page.locator('#tab-studio-view').click(timeout=10000)
        page.locator('#studio-file-input').set_input_files(PDF)
        page.locator('#studio-page-count').get_by_text('69').wait_for(timeout=45000)
        page.wait_for_timeout(1200)
        def rect(selector):
            e=page.locator(selector).first
            return e.evaluate("e=>{const r=e.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),display:getComputedStyle(e).display}}")
        data={s:rect(s) for s in ['#view-pdf-studio','.pdf-studio','.studio-thumbnails-bar','.studio-main-viewport','.ephemeral-work-notice','.studio-toolbar','#studio-annotate-ribbon','.studio-canvas-area','#studio-page-stack','#page-render-wrapper']}
        data['overflow']=page.evaluate('({doc:document.documentElement.scrollWidth,body:document.body.scrollWidth,viewport:innerWidth})')
        data['pageRendered']=page.locator('#page-render-wrapper').get_attribute('data-rendered')
        data['errors']=errors
        page.screenshot(path=f'reports/launch-audit-v3/{name}-layout-fixed.png',full_page=False)
        print(name,data)
        page.close()
    b.close()
