from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id77-') as temp:
    root=Path(temp);pdf=root/'mobile-actions.pdf'
    with fitz.open() as doc:
        for n in range(1,5):
            pg=doc.new_page();pg.insert_text((72,72),f'ID 77 mobile action page {n}')
        doc.save(pdf)
    app,base,_identity=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/studio',wait_until='domcontentloaded')
            page.locator('#studio-file-input').set_input_files(str(pdf))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='4' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=20000)
            page.locator('#btn-mode-organize').click()
            page.wait_for_function("document.querySelector('#btn-mode-organize')?.classList.contains('active')")
            page.wait_for_timeout(300)
            before_toggle=page.evaluate("()=>({mobile:matchMedia('(max-width:900px)').matches,button:document.querySelector('#studio-mobile-pages-btn')?.outerHTML,hidden:document.querySelector('#studio-mobile-pages-btn')?.hidden,rect:(()=>{let r=document.querySelector('#studio-mobile-pages-btn')?.getBoundingClientRect();return r?{x:r.x,y:r.y,w:r.width,h:r.height}:null})(),view:document.querySelector('#view-pdf-studio')?.hidden,errors:document.querySelector('#studio-loading-overlay')?.textContent})")
            if 'aria-expanded="true"' not in before_toggle['button']:
                page.locator('#studio-mobile-pages-btn').click()
            page.wait_for_timeout(200)
            after_toggle=page.evaluate("()=>({expanded:document.querySelector('#studio-mobile-pages-btn')?.getAttribute('aria-expanded'),shell:document.querySelector('#app-shell')?.className})")
            if after_toggle['expanded']!='true': raise RuntimeError(f'pages drawer did not open: before={before_toggle} after={after_toggle}')
            page.locator('#org-select-all-btn').click()
            page.wait_for_function("document.querySelector('#organizer-batch-bar')?.hidden===false",timeout=5000)
            page.locator('#studio-mobile-batch-slot .selection-action-clusters').wait_for(state='visible')
            actions=page.locator('#studio-mobile-batch-slot .selection-action-clusters')
            buttons=['batch-resize-btn','batch-move-up-btn','batch-move-down-btn','batch-ocr-btn']
            measurements={}
            for ident in buttons:
                locator=page.locator('#'+ident)
                box=locator.bounding_box()
                slot=page.locator('#studio-mobile-batch-slot').bounding_box()
                measurements[ident]={'visible':locator.is_visible(),'rect':box,'within_viewport':bool(box and box['x']>=0 and box['x']+box['width']<=390 and box['y']>=0 and box['y']+box['height']<=844),'within_action_panel':bool(box and slot and box['x']>=slot['x'] and box['x']+box['width']<=slot['x']+slot['width'] and box['y']>=slot['y'] and box['y']+box['height']<=slot['y']+slot['height'])}
            row=actions.evaluate("el=>({scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,scrollLeft:el.scrollLeft,overflowX:getComputedStyle(el).overflowX,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,rect:(r=>({x:r.x,y:r.y,width:r.width,height:r.height,right:r.right}))(el.getBoundingClientRect())})")
            zoom=page.locator('#zoom-select')
            zoom_value=zoom.locator('option:checked').inner_text()
            zoom_rect=zoom.bounding_box()
            page.screenshot(path=str(OUT/'id77-mobile-studio-actions.png'),full_page=True)
            result={'viewport':{'width':390,'height':844},'before_toggle':before_toggle,'after_toggle':after_toggle,'page_actions_visible':actions.is_visible(),'action_row':row,'buttons':measurements,'zoom_value':zoom_value,'zoom_rect':zoom_rect,'document_scroll_width':page.evaluate('document.documentElement.scrollWidth'),'page_errors':errors}
            (OUT/'browser-id77-mobile-studio-page-actions.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            assert all(item['visible'] and item['within_viewport'] and item['within_action_panel'] for item in measurements.values())
            assert row['scrollWidth'] <= row['clientWidth'] + 1 and '16' not in zoom_value and not errors
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
