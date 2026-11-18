from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id92-') as temp:
    root=Path(temp);pdf=root/'confirm-new-page.pdf'
    with fitz.open() as doc:
        pg=doc.new_page();pg.insert_text((72,72),'ID 92 preserve this document until confirmation.')
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
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];console=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda msg:console.append(msg.text) if msg.type=='error' else None)
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='1' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
                page.locator('#studio-close-doc-btn').click()
                dialog=page.locator('dialog.app-confirm-dialog')
                page.wait_for_function("document.querySelector('dialog.app-confirm-dialog')?.open===true")
                prompt=dialog.inner_text()
                dialog.locator('.app-confirm-cancel').click()
                page.wait_for_function("!document.querySelector('dialog.app-confirm-dialog')?.open")
                cancel_preserved=page.locator('#page-total-indicator').text_content().strip()=='1' and page.locator('.pdf-page-canvas').evaluate("el=>el.dataset.rendered==='true'") and page.locator('#studio-file-input').evaluate("el=>el.files.length===1")
                page.locator('#studio-close-doc-btn').click()
                page.wait_for_function("document.querySelector('dialog.app-confirm-dialog')?.open===true")
                page.locator('.app-confirm-accept').click()
                page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=20000)
                blank_count=page.locator('#page-total-indicator').text_content().strip()
                blank_canvas=page.locator('.pdf-page-canvas').evaluate("el=>({rendered:el.dataset.rendered,width:el.width,height:el.height})")
                page.screenshot(path=str(OUT/f'id92-blank-page-round{n}.png'))
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=20000)
                after_reload=page.locator('#page-total-indicator').text_content().strip()
                visible_errors=page.locator('.toast-notice.error,.studio-error').all_text_contents()
                empty_after_reload=page.locator('.studio-empty-state').is_visible()
                item={'round':n,'confirmation_prompt':prompt,'cancel_kept_source_pdf':cancel_preserved,'blank_page_count_after_confirm':blank_count,'blank_canvas':blank_canvas,'page_total_after_reload':after_reload,'empty_studio_after_reload':empty_after_reload,'visible_errors_after_reload':visible_errors,'page_errors':errors,'console_errors':console}
                rounds.append(item)
                print(json.dumps({'round':n,'prompt':prompt,'cancel_preserved':cancel_preserved,'blank_count':blank_count,'blank_canvas':blank_canvas,'after_reload':after_reload,'errors':visible_errors},indent=2))
                assert 'current PDF will be removed' in prompt
                assert cancel_preserved and blank_count=='1'
                assert blank_canvas['rendered']=='true' and blank_canvas['width']>0 and blank_canvas['height']>0
                assert after_reload=='0' and empty_after_reload and not visible_errors and not errors
                context.close()
            result={'rounds':rounds}
            (OUT/'browser-id92-new-page-confirmation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
