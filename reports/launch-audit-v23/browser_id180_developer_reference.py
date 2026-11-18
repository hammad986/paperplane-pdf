from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id180-') as temp:
    app, base, _ = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2): break
            except OSError: time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                context=browser.new_context()
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                response=page.goto(base+'/developers',wait_until='domcontentloaded')
                assert response and response.status==200
                page.locator('#view-api-docs').wait_for(state='visible')
                data=page.evaluate("""() => {const root=document.querySelector('#view-api-docs');return {title:document.title,heading:[...root.querySelectorAll('h1,h2')].filter(e=>e.getClientRects().length).map(e=>e.innerText.trim()),body:root.innerText,links:[...root.querySelectorAll('a')].map(a=>({text:a.innerText.trim(),href:a.getAttribute('href')}))}}""")
                assert data['heading']==['Developer REST API v1 reference'],data['heading']
                assert '/api/v1' in data['body'] and '2.0' not in data['body'],data['body'][:1000]
                assert any(x['href']=='/spec/swagger' for x in data['links']),data['links']
                assert any(x['href']=='/spec/redoc' for x in data['links']),data['links']
                swagger=page.request.get(base+'/spec/swagger')
                redoc=page.request.get(base+'/spec/redoc')
                schema=page.request.get(base+'/spec/openapi.json')
                assert swagger.status==redoc.status==schema.status==200,(swagger.status,redoc.status,schema.status)
                api_docs=page.request.get(base+'/api-docs',max_redirects=0)
                assert api_docs.status in (301,302,307,308) and api_docs.headers.get('location')=='/spec/swagger',(api_docs.status,api_docs.headers.get('location'))
                assert not errors,errors
                rounds.append({'round':n,'status':response.status,'heading':data['heading'],'containsV1Base':True,'noStaleV2Version':True,'swagger':swagger.status,'redoc':redoc.status,'schema':schema.status,'apiDocsRedirect':api_docs.status,'pageErrors':errors})
                context.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-id180-developer-reference.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
