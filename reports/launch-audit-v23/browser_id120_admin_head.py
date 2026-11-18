from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id120-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                get=page.goto(base+'/admin',wait_until='domcontentloaded');assert get.status==200
                head=page.evaluate("""async()=>{const r=await fetch('/admin',{method:'HEAD'});return {status:r.status,body:await r.text(),contentType:r.headers.get('content-type')}}""")
                assert head['status']==200 and head['body']=='' and head['contentType']=='text/html; charset=utf-8',head
                assert page.locator('body').inner_text().strip()
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id120-admin-head-round{number}.png'),full_page=True)
                rounds.append({'round':number,'get_status':get.status,'head_status':head['status'],'head_body_bytes':len(head['body']),'content_type':head['contentType'],'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds};(OUT/'browser-id120-admin-head.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
