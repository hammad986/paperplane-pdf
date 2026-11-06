from playwright.sync_api import sync_playwright
from pathlib import Path
import time
PDF = str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
BASE = 'http://127.0.0.1:8501'
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    for width,height,name in [(1440,1000,'desktop'),(390,844,'phone')]:
        context=b.new_context(viewport={'width':width,'height':height},device_scale_factor=1,is_mobile=width<600,has_touch=width<600)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.goto(BASE,wait_until='domcontentloaded',timeout=15000)
        page.evaluate("switchWorkspaceView('studio')")
        page.locator('#studio-file-input').set_input_files(PDF)
        page.locator('#studio-page-count').get_by_text('69').wait_for(timeout=45000)
        page.locator('#pdf-canvas[data-rendered="true"]').wait_for(timeout=45000)
        page.locator('.organizer-thumb-card').last.wait_for(timeout=45000)
        page.wait_for_timeout(400)
        data=page.evaluate("""()=>{const rect=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),display:getComputedStyle(e).display}};return {view:rect('#view-pdf-studio'),studio:rect('.pdf-studio'),thumbs:rect('.studio-thumbnails-bar'),viewport:rect('.studio-main-viewport'),notice:rect('.ephemeral-work-notice'),toolbar:rect('.studio-toolbar'),primary:rect('.studio-primary-ribbon'),secondary:rect('#studio-annotate-ribbon'),canvas:rect('#studio-canvas-area'),page:rect('#page-render-wrapper'),pageCanvas:rect('#pdf-canvas'),rendered:document.querySelector('#pdf-canvas')?.dataset.rendered,pageNumber:document.querySelector('#page-jump-input')?.value,total:document.querySelector('#page-total-indicator')?.textContent,thumbnailCount:document.querySelectorAll('.organizer-thumb-card').length,empty:!!document.querySelector('.studio-empty-state'),overflow:{document:document.documentElement.scrollWidth,body:document.body.scrollWidth,viewport:innerWidth}}}""")
        data['errors']=errors
        page.screenshot(path=f'reports/launch-audit-v3/{name}-layout-final.png')
        page.locator('#page-jump-input').fill('69')
        page.locator('#page-jump-input').press('Enter')
        page.locator('#studio-page-stack .studio-page-sheet[data-page="69"] canvas[data-rendered="true"]').wait_for(timeout=45000)
        page.wait_for_timeout(400)
        page.screenshot(path=f'reports/launch-audit-v3/{name}-page69-final.png')
        data['page69']=page.evaluate("""()=>{const area=document.querySelector('#studio-canvas-area').getBoundingClientRect();const slot=document.querySelector('#studio-page-stack .studio-page-sheet[data-page="69"]');const r=slot.getBoundingClientRect();return {input:document.querySelector('#page-jump-input').value,rendered:slot.querySelector('canvas').dataset.rendered,visible:r.bottom>area.top&&r.top<area.bottom,top:Math.round(r.top),bottom:Math.round(r.bottom),areaTop:Math.round(area.top),areaBottom:Math.round(area.bottom),active:slot.classList.contains('is-current')}}""")
        print(name,data)
        context.close()
    b.close()
