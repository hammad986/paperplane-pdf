from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent
ROUTES=['/compress-pdf','/organize-pdf','/ocr-pdf','/remove-pages-pdf','/repair-pdf','/rotate-pdf','/split-pdf','/scan-to-pdf','/jpg-to-pdf']

with TemporaryDirectory(prefix='paperplane-id82-') as temp:
    app,base,_identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            results=[]
            for route in ROUTES:
                response=page.goto(base+route,wait_until='domcontentloaded')
                first=page.evaluate("()=>({title:document.title,main:document.querySelector('.seo-content')?.innerText||'',operation:document.querySelector('.seo-content')?.dataset.operation||null,toolVisible:!!document.querySelector('#view-tool-desk:not([hidden])'),loading:[...document.querySelectorAll('*')].some(e=>e.children.length===0&&/loading.*details/i.test(e.textContent||''))})")
                page.wait_for_timeout(250)
                settled=page.evaluate("()=>({main:document.querySelector('.seo-content')?.innerText||'',operation:document.querySelector('.seo-content')?.dataset.operation||null,loading:[...document.querySelectorAll('*')].some(e=>e.children.length===0&&/loading.*details/i.test(e.textContent||''))})")
                has_details=bool(settled['main'].strip()) and len(settled['main'].strip())>70
                results.append({'route':route,'http_status':response.status if response else None,'first_paint_has_details':bool(first['main'].strip()) and len(first['main'].strip())>70,'settled_has_details':has_details,'first_paint_loading_flash':first['loading'],'settled_loading_text':settled['loading'],'operation':settled['operation'],'first_title':first['title']})
                assert response and response.status==200 and results[-1]['first_paint_has_details'] and has_details
                assert not first['loading'] and not settled['loading']
            result={'routes':results,'page_errors':errors}
            (OUT/'browser-id82-tool-details-first-paint.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            assert not errors
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
