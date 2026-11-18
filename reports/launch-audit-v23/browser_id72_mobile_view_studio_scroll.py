from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id72-') as temp:
    root=Path(temp);pdfs=[]
    for n in (1,2):
        path=root/f'local-merge-{n}.pdf'
        with fitz.open() as doc:
            page=doc.new_page();page.insert_text((72,72),f'ID 72 source page {n} unique mobile view studio marker')
            doc.save(path)
        pdfs.append(path)
    app,base,_identity=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            rounds=[]
            for n in (1,2):
                context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('#client-privacy-toggle')?.disabled === false")
                if not page.locator('#client-privacy-toggle').is_checked():page.locator('#client-privacy-toggle').check()
                page.locator('#file-input').set_input_files([str(x) for x in pdfs])
                page.wait_for_function("document.querySelector('#file-list')?.children.length >= 2",timeout=10000)
                page.locator('#run-button').click()
                page.wait_for_function("document.querySelector('#result-view-studio-btn')?.hidden === false",timeout=60000)
                result_panel=page.locator('#result')
                result_panel.scroll_into_view_if_needed()
                result_actions=page.locator('.result-actions')
                result_actions.scroll_into_view_if_needed()
                action_metrics=result_actions.evaluate("el=>({scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,rect:(r=>({x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}))(el.getBoundingClientRect()),buttons:[...el.querySelectorAll('a,button')].map(b=>{const r=b.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,top=document.elementFromPoint(x,y);return{text:b.innerText.trim(),visible:!!(r.width&&r.height),withinViewport:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,notCovered:top===b||b.contains(top),rect:{x:r.x,y:r.y,width:r.width,height:r.height}}})})")
                mobile_nav=page.locator('.mobile-workspace-bar').evaluate("el=>({rect:(r=>({x:r.x,y:r.y,width:r.width,height:r.height,top:r.top}))(el.getBoundingClientRect()),labels:[...el.querySelectorAll('.mobile-nav-btn span')].map(x=>({text:x.textContent.trim(),fontSize:getComputedStyle(x).fontSize}))})")
                page.evaluate("window.scrollTo(0,Math.max(document.body.scrollHeight,document.documentElement.scrollHeight))")
                await_position=page.evaluate("({windowY:window.scrollY,mainY:document.querySelector('.main-area')?.scrollTop||0})")
                page.screenshot(path=str(OUT/f'id72-mobile-result-round{n}.png'),full_page=True)
                page.locator('#result-view-studio-btn').click()
                page.wait_for_function("document.querySelector('#view-pdf-studio')?.hidden === false && document.querySelector('#page-total-indicator')?.textContent === '2' && document.querySelector('#studio-loading-overlay')?.hidden === true",timeout=30000)
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'",timeout=20000)
                toolbar=page.locator('#studio-toolbar').bounding_box()
                viewpos=page.evaluate("({windowY:window.scrollY,mainY:document.querySelector('.main-area')?.scrollTop||0})")
                export=page.locator('#save-studio-btn').bounding_box()
                visible=bool(toolbar and export and toolbar['y']>=0 and toolbar['y']<844 and export['y']>=0 and export['y']<844)
                page.screenshot(path=str(OUT/f'id72-mobile-studio-round{n}.png'),full_page=True)
                item={'round':n,'local_mode':page.locator('#client-privacy-toggle').is_checked(),'result_scroll_position':await_position,'result_actions':action_metrics,'mobile_nav':mobile_nav,'studio_scroll_position':viewpos,'toolbar_rect':toolbar,'export_rect':export,'toolbar_and_export_in_viewport':visible,'loaded_page_count':int(page.locator('#page-total-indicator').text_content()),'page_errors':errors}
                rounds.append(item)
                assert item['local_mode'] and item['loaded_page_count']==2 and visible and not errors
                assert all(x['visible'] and x['withinViewport'] and x['notCovered'] for x in action_metrics['buttons'])
                assert all(float(x['fontSize'].replace('px',''))>=11 for x in mobile_nav['labels'])
                context.close()
            result={'rounds':rounds}
            (OUT/'browser-id72-mobile-view-studio-scroll.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
