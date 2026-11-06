from playwright.sync_api import sync_playwright
from pathlib import Path
import time,json
PDF=str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
def sample(page,target,elapsed):
    return page.evaluate("""({target,elapsed})=>{const s=document.querySelector(`#studio-page-stack .studio-page-sheet[data-page="${target}"]`);const c=s?.querySelector('canvas');const a=document.querySelector('#studio-canvas-area').getBoundingClientRect();const r=s?.getBoundingClientRect();return {elapsed_s:elapsed,page:target,selected:document.querySelector('#page-jump-input').value,rendered:c?.dataset.rendered||'false',loading:s?.querySelector('.studio-page-loading')?.innerText||'',pageVisible:!!r&&r.bottom>a.top&&r.top<a.bottom,active:!!s?.classList.contains('is-current'),canvasSize:c?`${c.width}x${c.height}`:null}}""",{'target':target,'elapsed':elapsed})
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    page=b.new_page(viewport={'width':1440,'height':1000})
    page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded',timeout=15000)
    page.evaluate("switchWorkspaceView('studio')")
    page.locator('#studio-file-input').set_input_files(PDF)
    page.locator('#pdf-canvas[data-rendered="true"]').wait_for(timeout=45000)
    page.locator('.organizer-thumb-card').last.wait_for(timeout=45000)
    results=[]
    for target,via in [(69,'page-entry'),(1,'page-entry'),(35,'thumbnail')]:
        started=time.monotonic()
        if via=='thumbnail':
            page.locator(f'.organizer-thumb-card[data-page="{target}"]').click(force=True)
        else:
            page.locator('#page-jump-input').fill(str(target))
            page.locator('#page-jump-input').press('Enter')
        row={'via':via,'samples':[sample(page,target,0)]}
        page.wait_for_timeout(5000)
        row['samples'].append(sample(page,target,5))
        page.wait_for_timeout(10000)
        row['samples'].append(sample(page,target,15))
        results.append(row)
    page.locator('#page-jump-input').fill('1')
    page.locator('#page-jump-input').press('Enter')
    page.wait_for_timeout(350)
    page.mouse.move(900,500)
    page.mouse.wheel(0,1800)
    page.wait_for_timeout(900)
    scroll=page.evaluate("""()=>({activePage:document.querySelector('#page-jump-input').value,activeThumb:document.querySelector('.organizer-thumb-card.active')?.dataset.page,scrollTop:document.querySelector('#studio-canvas-area').scrollTop})""")
    print(json.dumps({'jumps':results,'continuous_scroll':scroll},indent=2))
    page.screenshot(path='reports/launch-audit-v3/desktop-jump-page35-final.png')
    b.close()
