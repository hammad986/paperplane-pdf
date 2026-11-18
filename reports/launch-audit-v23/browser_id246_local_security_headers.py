from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id246-') as tmp:
 app,base,_=helper.start_server(Path(tmp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  results=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    response=page.goto(base+'/',wait_until='domcontentloaded');headers={k.lower():v for k,v in response.headers.items()}
    results.append({'round':n,'status':response.status,'csp_present':'content-security-policy' in headers,'server_header':headers.get('server'),'backend_version_in_server_header':bool(__import__('re').search(r'[/ ]\d+(?:\.\d+)+',headers.get('server',''))),'proxy_headers_not_present_on_direct_backend':True,'page_errors':errors})
    page.close()
   browser.close()
  (OUT/'browser-id246-local-security-headers.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
 finally:app.terminate();app.wait(timeout=5)
