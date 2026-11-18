from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id218-') as temp:
    tmp=Path(temp); pdf=tmp/'test-text-10page.pdf'
    with fitz.open() as doc:
        for n in range(1,11):
            page=doc.new_page(); page.insert_text((72,72),f'AI restore race marker page {n}')
        doc.save(pdf)
    app,base,_=helper.start_server(tmp/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True); rounds=[]
            for n in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900}); page=context.new_page(); errors=[]
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(base+'/',wait_until='domcontentloaded')
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)
                page.locator('#tab-ai-view').click()
                page.wait_for_function("!document.querySelector('#view-ai-studio')?.hidden")
                page.locator('#ai-file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden===false && [...document.querySelectorAll('.chat-bubble')].some(x=>x.innerText.includes('Your PDF is ready'))",timeout=20000)
                initial=page.evaluate("""()=>({file:document.querySelector('#ai-doc-name')?.textContent,ready:document.querySelector('#ai-doc-meta')?.textContent,emptyVisible:!document.querySelector('#ai-empty-state')?.hidden,greetings:[...document.querySelectorAll('.chat-bubble')].filter(x=>x.innerText.includes('Your PDF is ready')).length})""")
                assert initial['file']=='test-text-10page.pdf' and initial['greetings']==1 and not initial['emptyVisible'],initial
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden===false && [...document.querySelectorAll('.chat-bubble')].some(x=>x.innerText.includes('Your PDF is ready')) && document.querySelector('#ai-doc-meta')?.textContent.includes('10 pages')",timeout=25000)
                await_state=page.evaluate("""()=>({file:document.querySelector('#ai-doc-name')?.textContent,ready:document.querySelector('#ai-doc-meta')?.textContent,emptyVisible:!document.querySelector('#ai-empty-state')?.hidden,greetings:[...document.querySelectorAll('.chat-bubble')].filter(x=>x.innerText.includes('Your PDF is ready')).length,documentWidth:document.documentElement.scrollWidth})""")
                assert await_state['file']=='test-text-10page.pdf' and '10 pages' in await_state['ready'] and await_state['greetings']==1 and not await_state['emptyVisible'] and not errors,await_state
                page.screenshot(path=str(OUT/f'id218-ai-restore-round{n}.png'))
                rounds.append({'round':n,'before_reload':initial,'after_reload':await_state,'page_errors':errors}); context.close()
            browser.close()
        result={'rounds':rounds}; (OUT/'browser-id218-ai-restore-race.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
    finally:
        app.terminate(); app.wait(timeout=5)
