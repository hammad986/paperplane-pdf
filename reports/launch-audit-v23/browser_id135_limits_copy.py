from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id135-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));routes=[]
    for path,tool in (('/summarize-pdf','PDF Summarizer'),('/mask-aadhaar-card-online','Aadhaar')):
     resp=page.goto(base+path,wait_until='domcontentloaded');page.wait_for_timeout(350)
     lines=page.locator('body').inner_text().splitlines();limits=[x.strip() for x in lines if ('MB each' in x or 'files per run' in x or 'file per run' in x) and x.strip()]
     wrong=[x for x in limits if 'Merge supports' in x or 'Merge,' in x];truncated=[x for x in limits if x.endswith('…') or x.endswith('...')]
     routes.append({'path':path,'status':resp.status if resp else None,'visible_limits':limits,'mentions_wrong_merge_operation':bool(wrong),'truncated_limits':bool(truncated),'pricing_link':page.locator('a[href*="pricing#pricing-limits-table"]').count()})
     assert resp and resp.status==200 and limits and not wrong and not truncated
    rounds.append({'round':n,'routes':routes,'page_errors':errors});assert not errors;c.close()
   res={'rounds':rounds};(OUT/'browser-id135-tool-specific-limits.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
