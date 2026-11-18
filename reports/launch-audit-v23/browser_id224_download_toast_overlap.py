from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id224-') as temp:
    root=Path(temp);source=root/'toast-overlap.pdf'
    with fitz.open() as doc:
        for n in range(4):doc.new_page().insert_text((72,72),f'ID224 toast action marker {n+1}')
        doc.save(source)
    app,base,identity=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);rounds=[]
            for n in (1,2):
                ctx=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,accept_downloads=True)
                ctx.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base,'httpOnly':True}])
                page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
                local=page.locator('#client-privacy-toggle')
                if local.is_checked():local.evaluate("el=>{el.checked=false;el.dispatchEvent(new Event('change',{bubbles:true}))}")
                page.locator('#file-input').set_input_files(str(source));page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
                link=page.locator('#result-download-link')
                with page.expect_download(timeout=15000) as evt:link.click()
                out=root/f'id224-round{n}.pdf';evt.value.save_as(out)
                with fitz.open(out) as result:assert len(result)==4 and all(f'ID224 toast action marker {i}' in ''.join(pg.get_text() for pg in result) for i in range(1,5))
                page.wait_for_function("document.querySelector('.toast-notice')?.innerText.includes('Download complete')",timeout=5000)
                geometry=page.evaluate("""()=>{const t=document.querySelector('.toast-notice'),a=document.querySelector('#result .result-actions');if(!t||!a)return null;const r=e=>{const x=e.getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom,width:x.width,height:x.height}};const x=r(t),y=r(a);return {toast:x,actions:y,overlap:x.left<y.right&&x.right>y.left&&x.top<y.bottom&&x.bottom>y.top,viewport:{width:innerWidth,height:innerHeight}}}""")
                assert geometry and not errors,(geometry,errors)
                page.screenshot(path=str(OUT/f'id224-download-toast-round{n}.png'))
                rounds.append({'round':n,'toast_and_actions':geometry,'download_bytes':out.stat().st_size,'pages':4,'page_errors':errors})
                ctx.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id224-download-toast-overlap.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
