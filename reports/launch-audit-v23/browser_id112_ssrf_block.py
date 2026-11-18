from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, threading, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

hits=[]
class Canary(BaseHTTPRequestHandler):
    def do_GET(self):
        hits.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'CANARY SHOULD NOT BE FETCHED')
    def log_message(self,*_):pass

with TemporaryDirectory(prefix='paperplane-id112-') as temp:
    canary=ThreadingHTTPServer(('127.0.0.1',0),Canary);threading.Thread(target=canary.serve_forever,daemon=True).start()
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
                page.goto(base+'/html-to-pdf',wait_until='domcontentloaded')
                page.locator('#url').fill(f'http://127.0.0.1:{canary.server_port}/secret')
                assert not page.locator('#run-button').is_disabled()
                with page.expect_response('**/api/jobs') as event:page.locator('#run-button').click()
                accepted=event.value;assert accepted.status==202,accepted.status
                job=accepted.json();status_url=job['status_url'];result=None
                for _ in range(80):
                    response=page.request.get(base+status_url)
                    result=response.json()
                    if result.get('status') in ('failed','completed','error'):break
                    time.sleep(.2)
                assert result and result.get('status') in ('failed','error'),result
                failure=json.dumps(result).lower()
                assert any(word in failure for word in ('ssrf','private','unsafe','blocked','forbidden','access to host')),failure
                assert not hits,hits
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id112-ssrf-block-round{number}.png'),full_page=True)
                rounds.append({'round':number,'job_status':result.get('status'),'failure':str(result)[:240],'canary_http_hits':len(hits),'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'canary_hits':hits};(OUT/'browser-id112-ssrf-block.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5);canary.shutdown();canary.server_close()
