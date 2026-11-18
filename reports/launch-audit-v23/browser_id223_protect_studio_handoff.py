from pathlib import Path
from tempfile import TemporaryDirectory
import base64,fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id223-') as temp:
    root=Path(temp); source=root/'protected-studio.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((72,72),'ID223 protected Studio handoff marker')
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
                page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True);errors=[]; logs=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('console',lambda m:logs.append(f'{m.type}: {m.text}') if m.type in ('error','warning') else None)
                page.goto(base+'/protect-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
                page.locator('#file-input').set_input_files(str(source));page.locator('#password').fill('protect-test-pass');page.locator('#run-button').click()
                page.locator('#result-view-studio-btn').wait_for(state='visible',timeout=20000)
                download_href=page.locator('#result-download-link').get_attribute('href')
                page.locator('#result-view-studio-btn').click()
                page.wait_for_function("!document.querySelector('#view-pdf-studio')?.hidden",timeout=10000)
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
                state=page.evaluate("""()=>({activeView:sessionStorage.getItem('paperplane-active-view'),studioVisible:!document.querySelector('#view-pdf-studio')?.hidden,pages:document.querySelector('#page-total-indicator')?.textContent,rendered:document.querySelector('#pdf-canvas')?.dataset.rendered,emptyVisible:document.querySelector('#studio-empty-state')?.hidden===false,loading:document.querySelector('#studio-loading-overlay')?.hidden,storageHasPassword:Object.values(sessionStorage).some(x=>x.includes('protect-test-pass'))})""")
                assert state['activeView']=='studio' and state['studioVisible'] and state['pages']=='1' and state['rendered']=='true' and not state['emptyVisible'] and not state['storageHasPassword'] and not errors,(state,errors,logs)
                payload=page.evaluate("""async()=>{const f=window.PaperplaneEditor?.editorState?.sourceFile;if(!f)return null;const b=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<b.length;i+=0x8000)s+=String.fromCharCode(...b.subarray(i,i+0x8000));return {name:f.name,size:f.size,bytes:btoa(s)}}""")
                assert payload and payload['name']=='protected-studio_protect.pdf'
                raw=base64.b64decode(payload['bytes'])
                out=root/f'id223-protected-{n}.pdf';out.write_bytes(raw)
                with fitz.open(out) as pdf:
                    assert pdf.is_encrypted and pdf.needs_pass and pdf.authenticate('protect-test-pass') and 'ID223 protected Studio handoff marker' in pdf[0].get_text()
                page.screenshot(path=str(OUT/f'id223-protect-studio-round{n}.png'))
                rounds.append({'round':n,'handoff':state,'in_memory_filename':payload['name'],'download_bytes':out.stat().st_size,'encrypted_content_checked':True,'page_errors':errors,'console_warnings':logs});page.context.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id223-protect-studio-handoff.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
