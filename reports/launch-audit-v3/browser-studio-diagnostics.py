from playwright.sync_api import sync_playwright
from pathlib import Path
PDF = str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    page=b.new_page(viewport={'width':1440,'height':1000})
    logs=[]
    page.on('console',lambda msg: logs.append(f'{msg.type}: {msg.text}') if msg.type=='error' else None)
    page.on('pageerror',lambda err: logs.append(f'PAGE ERROR: {err}'))
    page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded',timeout=15000)
    page.evaluate("switchWorkspaceView('studio')")
    page.locator('#studio-file-input').set_input_files(PDF)
    page.wait_for_timeout(6000)
    data=page.evaluate("""()=>({active:document.querySelector('#view-pdf-studio').hidden,notice:!!document.querySelector('#studio-canvas-area .ephemeral-work-notice'),empty:[...document.querySelectorAll('#studio-canvas-area .studio-empty-state')].map(e=>e.innerText),canvasChildren:[...document.querySelector('#studio-canvas-area').children].map(e=>({tag:e.tagName,cls:e.className,txt:e.innerText?.slice(0,100)})),stackDisplay:getComputedStyle(document.querySelector('#studio-page-stack')).display,slots:document.querySelectorAll('#studio-page-stack .studio-page-sheet').length,rendered:document.querySelector('#page-render-wrapper')?.dataset.rendered,loading:document.querySelector('#page-render-wrapper .studio-page-loading')?.outerHTML,canvas:document.querySelector('#page-render-wrapper .pdf-page-canvas')?.getBoundingClientRect().toJSON(),thumbs:document.querySelectorAll('.organizer-thumb-card').length,readout:document.querySelector('#page-indicator').innerText})""")
    print(data)
    print(logs)
    page.screenshot(path='reports/launch-audit-v3/desktop-debug.png')
    b.close()
