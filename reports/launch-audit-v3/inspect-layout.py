from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width":1440,"height":1000})
    page.goto('http://127.0.0.1:8501', wait_until='domcontentloaded', timeout=10000)
    page.wait_for_timeout(1000)
    page.evaluate("document.getElementById('app-shell').classList.add('studio-active'); document.getElementById('view-pdf-studio').hidden=false")
    for s in ['#view-pdf-studio','.ephemeral-work-notice','.pdf-studio','.studio-thumbnails-bar','.studio-main-viewport','.studio-toolbar','.studio-canvas-area','#studio-page-stack']:
        e=page.locator(s).first
        print(s, e.evaluate("e=>({rect:(r=>({x:r.x,y:r.y,w:r.width,h:r.height}))(e.getBoundingClientRect()),display:getComputedStyle(e).display,gridColumn:getComputedStyle(e).gridColumn,gridRow:getComputedStyle(e).gridRow,position:getComputedStyle(e).position,order:getComputedStyle(e).order})"))
    b.close()
