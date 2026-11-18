from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id143-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1104,'height':760});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));resp=page.goto(base+'/developers',wait_until='domcontentloaded');copy=page.locator('.api-docs-hero-box p').inner_text();result={'round':n,'status':resp.status if resp else None,'banner_copy':copy,'space_before_key_example':'keys (' in copy,'missing_space':'keys(' in copy,'page_errors':errors};assert resp and resp.status==200 and result['space_before_key_example'] and not result['missing_space'] and not errors
    page.screenshot(path=str(OUT/f'id143-developer-banner-round{n}.png'));rounds.append(result);c.close()
   data={'rounds':rounds};(OUT/'browser-id143-developer-banner-spacing.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
