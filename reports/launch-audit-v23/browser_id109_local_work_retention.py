from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

async_keys="""()=>new Promise((resolve,reject)=>{const r=indexedDB.open('paperplane-local-work',1);r.onsuccess=()=>{const db=r.result;const q=db.transaction('work','readonly').objectStore('work').getAllKeys();q.onsuccess=()=>{resolve(q.result.map(String));db.close()};q.onerror=()=>reject(q.error)};r.onerror=()=>reject(r.error)})"""

with TemporaryDirectory(prefix='paperplane-id109-') as temp:
    root=Path(temp);pdf=root/'local-retention.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Local device persistence retention sample.');doc.save(pdf)
    app,base,_=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
                page.locator('#ai-file-input').set_input_files(str(pdf))
                page.wait_for_function("window.state?.files?.some(f=>f.name==='local-retention.pdf')",timeout=15000)
                page.wait_for_function("indexedDB.databases().then(db=>db.some(x=>x.name==='paperplane-local-work'))",timeout=10000)
                page.wait_for_timeout(250)
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='1' && document.querySelector('#studio-loading-overlay')?.hidden",timeout=20000)
                page.wait_for_timeout(250)
                before=page.evaluate(async_keys)
                assert any('ai-pdf' in k for k in before) and any('studio-pdf' in k for k in before),before
                page.goto(base+'/privacy',wait_until='domcontentloaded')
                privacy=page.locator('body').inner_text()
                assert 'Browser-saved Studio and AI Docs work remains on this device until you clear it.' in privacy
                page.goto(base+'/settings',wait_until='domcontentloaded')
                page.locator('#settings-tab-btn-privacy').click()
                page.evaluate('window.confirmAction=async()=>true')
                page.locator('#studio-clear-work-btn').click()
                page.get_by_text('Saved browser PDFs, AI chat, and page position cleared',exact=True).wait_for(timeout=10000)
                after=page.evaluate(async_keys);assert not after,after
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.wait_for_function("!window.state?.studio?.pdfDoc && document.querySelector('#studio-canvas-area .studio-empty-state')",timeout=15000)
                page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
                page.wait_for_timeout(250)
                assert not page.locator('#chat-messages').inner_text().strip() or 'upload' in page.locator('#chat-messages').inner_text().lower()
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id109-local-work-clear-round{number}.png'),full_page=True)
                rounds.append({'round':number,'saved_studio_and_ai_records_before_clear':before,'records_after_clear':after,'reload_empty':True,'privacy_disclosure':True,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'scope':'local IndexedDB records are not covered by server job expiry; explicit Clear Studio removes Studio and AI saved work'}
        (OUT/'browser-id109-local-work-retention.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
