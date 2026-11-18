from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id1-echo-') as temp:
    source=Path(temp)/'provider-echo.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'The planned programme covers planning phases and operational workstreams.')
        doc.save(source)
    app,base,_identity=helper.start_server(Path(temp)/'db')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        results=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                context=browser.new_context(viewport={'width':1280,'height':800},accept_downloads=True)
                def operations_override(route):
                    response=route.fetch();data=response.json()
                    if isinstance(data.get('translate'),dict):
                        data['translate']['available']=True;data['translate']['status']='AVAILABLE'
                    route.fulfill(response=response,content_type='application/json',body=json.dumps(data))
                context.route('**/api/operations',operations_override)
                context.route('**/api/ai/translate',lambda route: route.fulfill(status=422,content_type='application/json',body=json.dumps({'detail':'Only 0% of source text changed during translation (minimum 10%). No translated PDF was produced.'})) if route.request.method=='POST' else route.continue_())
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/translate-pdf',wait_until='domcontentloaded');page.wait_for_function("state.operation==='translate'")
                page.locator('#file-input').set_input_files(str(source))
                page.wait_for_function("state.files.length===1 && !document.querySelector('#run-button').disabled")
                page.evaluate("""()=>{const select=document.querySelector('#target_language');if(select&&!select.options.length){select.add(new Option('es (Spanish)','es'))}if(select){select.value='es';select.dispatchEvent(new Event('change',{bubbles:true}))}}""")
                with page.expect_response(lambda r:'/api/ai/translate' in r.url and r.request.method=='POST') as posted:
                    page.locator('#run-button').click()
                response=posted.value
                page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden")
                title=page.locator('#result-title').inner_text();body=page.locator('#result-meta').inner_text()
                assert response.status==422 and title=='Processing failed',(response.status,title,body)
                assert '0%' in body and 'minimum 10%' in body
                assert page.locator('#result-download-link').is_hidden()
                assert 'Partial translation ready' not in page.locator('#result').inner_text()
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id1-zero-change-rejected-round{n}.png'))
                results.append({'round':n,'http_status':response.status,'title':title,'message':body,'download_available':not page.locator('#result-download-link').is_hidden(),'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':results,'mock':'server returned the actual 422 message for provider echo under 10% content change'}
        (OUT/'browser-id1-zero-change-rejected.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:app.terminate();app.wait(timeout=5)
