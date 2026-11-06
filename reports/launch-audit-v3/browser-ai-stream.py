from playwright.sync_api import sync_playwright
from pathlib import Path
import time,json
PDF=str(Path('runtime_data_codex_audit/notes_69pages_audit.pdf').resolve())
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    for width,height,name in [(1440,1000,'desktop'),(375,812,'phone')]:
        context=b.new_context(viewport={'width':width,'height':height},is_mobile=width<600,has_touch=width<600)
        page=context.new_page(); errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded',timeout=15000)
        page.evaluate("switchWorkspaceView('ai')")
        page.locator('#ai-file-input').set_input_files(PDF)
        page.locator('#ai-doc-name').wait_for(timeout=10000)
        page.locator('#chat-input').fill('Summarize polynomial degrees and vector orthogonality.')
        started=time.monotonic()
        page.locator('#chat-send-btn').click()
        transitions=[]; prior=-1; deadline=started+30
        while time.monotonic()<deadline:
            txt=page.locator('.ai-stream-text').last.inner_text() if page.locator('.ai-stream-text').count() else ''
            if len(txt)>prior:
                transitions.append({'elapsed_ms':round((time.monotonic()-started)*1000),'characters':len(txt),'prefix':txt[:70]})
                prior=len(txt)
            if page.locator('.ai-stage-line').last.inner_text().strip().endswith('Complete'):
                break
            page.wait_for_timeout(15)
        result=page.evaluate("""()=>{const s=document.querySelector('.ai-stream-bubble');return {answer:s?.querySelector('.ai-stream-text')?.innerText,citations:[...s?.querySelectorAll('.ai-citation-tag')||[]].map(e=>e.innerText),mode:s?.querySelector('.ai-response-mode')?.innerText,stage:s?.querySelector('.ai-stage-line')?.innerText,timeline:[...s?.querySelectorAll('[data-ai-stage]')||[]].map(e=>({name:e.innerText,state:e.className})),layout:{document:document.documentElement.scrollWidth,body:document.body.scrollWidth,viewport:innerWidth,chat:document.querySelector('.ai-studio-container').getBoundingClientRect().toJSON(),input:document.querySelector('#chat-input').getBoundingClientRect().toJSON()}}}""")
        result['elapsed_seconds']=round(time.monotonic()-started,2); result['transitions']=transitions[:15]; result['errors']=errors
        page.screenshot(path=f'reports/launch-audit-v3/{name}-ai-stream.png')
        page.reload(wait_until='domcontentloaded',timeout=15000)
        page.wait_for_timeout(1200)
        result['reload']={'toast':page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else None,'chatBubbleCount':page.locator('#chat-messages .chat-bubble.user').count(),'confirmShown':False}
        print(name,json.dumps(result,ensure_ascii=False))
        context.close()
    b.close()
