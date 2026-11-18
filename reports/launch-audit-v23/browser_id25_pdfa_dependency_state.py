from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id25-pdfa-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        results=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                response=page.goto(base+'/pdf-to-pdfa',wait_until='domcontentloaded');assert response.status==200
                notice=page.locator('#tool-availability-notice');notice.wait_for(state='visible',timeout=15000)
                text=notice.inner_text();assert 'Ghostscript' in text,text
                assert page.locator('#run-button').is_disabled()
                catalog=page.request.get(base+'/api/operations').json()['pdf_to_pdfa']
                assert catalog['available'] is False and catalog['status']=='DEPENDENCY_MISSING',catalog
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id25-pdfa-prerequisite-round{number}.png'))
                results.append({'round':number,'notice':text,'run_disabled':True,'catalog_status':catalog['status'],'prerequisite':catalog['prerequisite'],'page_errors':errors})
                page.close()
            browser.close()
        data={'rounds':results};(OUT/'browser-id25-pdfa-dependency-state.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
