from pathlib import Path
from tempfile import TemporaryDirectory
import base64, json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-280-281-') as temp:
    fixture=Path(temp)/'studio-fixture.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_text((72,72),'STUDIO CONFIRMATION FIXTURE')
        pdf.save(fixture)
    encoded=base64.b64encode(fixture.read_bytes()).decode()
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.add_init_script("window.__confirmCalls=[]; window.confirm=(message)=>{window.__confirmCalls.push(String(message));return true};")
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.wait_for_function("!document.body.classList.contains('auth-pending') && !document.querySelector('#view-pdf-studio').hidden")
                empty=page.evaluate("""() => ({confirmCalls:[...window.__confirmCalls], noDoc:document.querySelector('#studio-page-count')?.textContent.trim()||'', url:location.pathname})""")
                assert empty['confirmCalls']==[],empty
                page.evaluate("""async (b64) => {const raw=atob(b64);const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));await loadDocumentIntoStudio(new File([bytes],'studio-fixture.pdf',{type:'application/pdf'}));return true}""",encoded)
                page.wait_for_function("document.querySelectorAll('#studio-page-stack canvas').length>0")
                loaded=page.evaluate("""() => ({pages:document.querySelectorAll('#studio-page-stack canvas').length,
                    counter:document.querySelector('#studio-page-count')?.textContent.trim()||'',
                    confirmCalls:[...window.__confirmCalls],url:location.pathname})""")
                assert loaded['counter']=='1' and loaded['confirmCalls']==[],loaded
                page.goto(base+'/',wait_until='domcontentloaded')
                page.wait_for_function("!document.body.classList.contains('auth-pending') && !document.querySelector('#view-tool-desk-directory').hidden")
                root=page.evaluate("""() => ({path:location.pathname,active:state.activeView,studioHidden:document.querySelector('#view-pdf-studio').hidden,confirmCalls:[...window.__confirmCalls]})""")
                assert root['path']=='/' and root['active']=='tool-desk' and root['studioHidden'] and not root['confirmCalls'],root
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id280-281-round{n}.png'))
                rounds.append({'round':n,'empty_studio':empty,'loaded_studio':loaded,'root_from_studio':root,'page_errors':errors})
                page.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-ids280-281.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
