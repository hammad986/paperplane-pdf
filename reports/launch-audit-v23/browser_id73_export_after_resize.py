from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id73-') as temp:
    root=Path(temp);pdf=root/'resize-5-pages.pdf'
    with fitz.open() as doc:
        for n in range(1,6):
            pg=doc.new_page();pg.insert_text((72,72),f'ID 73 resize export page {n} unique marker RZ{n:02d}')
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
            rounds=[]
            for n in (1,2):
                context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,accept_downloads=True)
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='5' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=20000)
                page.evaluate("document.querySelector('#save-studio-btn')?.focus()")
                page.set_viewport_size({'width':1366,'height':900})
                page.wait_for_function("window.matchMedia('(min-width: 901px)').matches && document.querySelector('#page-total-indicator')?.textContent==='5'",timeout=10000)
                page.wait_for_function("document.querySelector('.studio-primary-ribbon > .studio-export-group #save-studio-btn') !== null",timeout=10000)
                export_focus_preserved=page.evaluate("document.activeElement?.id==='save-studio-btn'")
                zoom_controls=page.evaluate("""()=>['#zoom-out-btn','#zoom-select','#zoom-in-btn'].map(selector=>{const element=document.querySelector(selector);const rect=element?.getBoundingClientRect();return {selector,insideDesktopRibbon:!!element?.closest('.studio-primary-ribbon'),width:rect?.width||0,height:rect?.height||0,visible:!!rect&&rect.width>0&&rect.height>0}})""")
                assert all(control['insideDesktopRibbon'] and control['visible'] for control in zoom_controls),zoom_controls
                for target_page in (2,3,4):
                    page.locator('#next-page-btn').click()
                    page.wait_for_function("(n)=>document.querySelector('#page-jump-input')?.value===String(n)",arg=target_page,timeout=8000)
                page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"4\"] .pdf-page-canvas')?.dataset.rendered==='true'",timeout=15000)
                page4=page.locator('.studio-page-sheet[data-page="4"] .pdf-page-canvas').evaluate("el=>({page:el.closest('.studio-page-sheet').dataset.page,rendered:el.dataset.rendered,rect:(r=>({width:r.width,height:r.height}))(el.getBoundingClientRect())})")
                page.locator('#next-page-btn').click()
                try:
                    page.wait_for_function("document.querySelector('#page-jump-input')?.value==='5' && document.querySelector('.studio-page-sheet[data-page=\"5\"] .pdf-page-canvas')?.dataset.rendered==='true'",timeout=25000)
                except Exception:
                    diagnostics=page.evaluate("()=>({page:document.querySelector('#page-jump-input')?.value,total:document.querySelector('#page-total-indicator')?.textContent,canvas:document.querySelector('.studio-page-sheet[data-page=\"5\"] .pdf-page-canvas')?.dataset.rendered,loading:document.querySelector('.studio-page-sheet[data-page=\"5\"] .studio-page-loading')?.textContent,loaderHidden:document.querySelector('.studio-page-sheet[data-page=\"5\"] .studio-page-loading')?.hidden,errors:[...document.querySelectorAll('.studio-error')].map(x=>x.textContent)})")
                    page.screenshot(path=str(OUT/f'id73-page5-timeout-round{n}.png'))
                    raise RuntimeError(f'page 5 failed after resize: {diagnostics}')
                page5=page.locator('.studio-page-sheet[data-page="5"] .pdf-page-canvas').evaluate("el=>({page:el.closest('.studio-page-sheet').dataset.page,rendered:el.dataset.rendered,rect:(r=>({width:r.width,height:r.height}))(el.getBoundingClientRect())})")
                with page.expect_download(timeout=30000) as download_info:
                    page.locator('#save-studio-btn').click()
                download=download_info.value
                target=root/f'id73-round{n}-{Path(download.suggested_filename).name}'
                download.save_as(target)
                with fitz.open(target) as output:
                    pages=len(output);text='\n'.join(pg.get_text() for pg in output)
                item={'round':n,'input_pages':5,'mobile_to_desktop_resize':True,'export_control_restored_to_desktop_ribbon':True,'export_focus_preserved_on_resize':export_focus_preserved,'zoom_controls_restored_to_desktop_ribbon':zoom_controls,'page4':page4,'page5':page5,'export_filename':download.suggested_filename,'export_pages':pages,'all_page_markers_present':all(f'RZ{i:02d}' in text for i in range(1,6)),'export_bytes':target.stat().st_size,'page_errors':errors}
                rounds.append(item)
                page.screenshot(path=str(OUT/f'id73-resize-round{n}.png'))
                assert page4['rendered']=='true' and page5['rendered']=='true' and page4['page']=='4' and page5['page']=='5'
                assert export_focus_preserved and pages==5 and item['all_page_markers_present'] and target.stat().st_size>500 and not errors
                context.close()
            result={'rounds':rounds}
            (OUT/'browser-id73-export-after-resize.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
