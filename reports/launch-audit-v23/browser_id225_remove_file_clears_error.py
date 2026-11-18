from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id225-') as temp:
    root=Path(temp);source=root/'summary-failure.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((72,72),'ID225 controlled summary failure fixture')
        doc.save(source)
    app,base,_=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);rounds=[]
            for n in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/summarize-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
                page.evaluate("""()=>{state.files=[new File(['controlled summary failure fixture'],'summary-failure.pdf',{type:'application/pdf'})];renderFiles();showResult('AI service returned an empty or invalid response',true)}""")
                page.locator('[data-remove-file="0"]').wait_for(state='visible')
                page.wait_for_function("!document.querySelector('#result')?.hidden && document.querySelector('#result-title')?.textContent==='Processing failed'",timeout=15000)
                error_before=page.locator('#result-meta').inner_text()
                page.locator('[data-remove-file="0"]').click()
                after=page.evaluate("""()=>({resultHidden:document.querySelector('#result')?.hidden,fileRows:document.querySelectorAll('#file-list .file-row-card').length,runDisabled:document.querySelector('#run-button')?.disabled,meta:document.querySelector('#result-meta')?.textContent})""")
                page.screenshot(path=str(OUT/f'id225-remove-error-round{n}.png'))
                rounds.append({'round':n,'error_before_remove':error_before,'after_remove':after,'page_errors':errors})
                assert after['resultHidden'] and after['fileRows']==0 and after['meta']=='' and after['runDisabled'] and not errors,(after,errors)
                page.context.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id225-remove-file-error.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
