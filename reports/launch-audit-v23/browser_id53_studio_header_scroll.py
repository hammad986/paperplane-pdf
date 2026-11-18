from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id53-') as temp:
    root=Path(temp)
    pdf=root/'studio-header-67-pages.pdf'
    with fitz.open() as doc:
        for n in range(1,68):
            page=doc.new_page()
            page.insert_text((72,72),f'ID 53 current-build Studio header fixture page {n}')
        doc.save(pdf)
    app,base,identity=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1104,'height':760})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.context.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base}])
            page.goto(base+'/studio',wait_until='domcontentloaded')
            page.locator('#studio-file-input').set_input_files(str(pdf))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67' && document.querySelector('#studio-loading-overlay')?.hidden === true",timeout=30000)
            page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'",timeout=20000)
            selectors=['#studio-toolbar','#save-studio-btn','.breadcrumb-trail','#studio-thumbnails-bar']
            def measure():
                return page.evaluate("sels=>Object.fromEntries(sels.map(s=>{const e=document.querySelector(s);if(!e)return[s,null];const r=e.getBoundingClientRect();const st=getComputedStyle(e);return[s,{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,display:st.display,visibility:st.visibility,position:st.position,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}]}))",selectors)
            before=measure()
            page.screenshot(path=str(OUT/'id53-studio-header-before-scroll.png'))
            page.evaluate("window.scrollTo(0,650); document.querySelector('.studio-main-viewport')?.scrollTo(0,650)")
            page.wait_for_timeout(250)
            after=measure()
            page.screenshot(path=str(OUT/'id53-studio-header-after-scroll.png'))
            result={'viewport':{'width':1104,'height':760},'source_pages':67,'before_scroll':before,'after_scroll':after,'export_visible_after_scroll':bool(after['#save-studio-btn'] and after['#save-studio-btn']['display']!='none' and after['#save-studio-btn']['y']>=0 and after['#save-studio-btn']['bottom']<=760),'page_errors':errors}
            (OUT/'browser-id53-studio-header-scroll.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            assert result['export_visible_after_scroll'] and not errors
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
