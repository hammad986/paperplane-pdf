import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id139-sidebar-available-tools-pages.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
routes=['/apps','/download','/privacy','/terms','/mask-aadhaar-card-online']
with TemporaryDirectory(prefix='paperplane-id139-') as td:
 app,base,_=h.start_server(Path(td)/'data')
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1366,'height':900});errs=[];page.on('pageerror',lambda x:errs.append(str(x)));page.on('console',lambda m:errs.append(m.text) if m.type=='error' else None);checks=[]
   for route in routes:
    r=page.goto(base+route,wait_until='domcontentloaded');first_count=page.locator('#sidebar-tools-container .sidebar-tool-item').count();page.wait_for_timeout(1000);settled_count=page.locator('#sidebar-tools-container .sidebar-tool-item').count();checks.append({'route':route,'status':r.status if r else None,'first_paint_tool_count':first_count,'settled_tool_count':settled_count,'sidebar_visible':page.locator('#sidebar-tools-container').is_visible() if page.locator('#sidebar-tools-container').count() else False,'sidebar_text':page.locator('#sidebar-tools-container').inner_text()[:120] if page.locator('#sidebar-tools-container').count() else ''})
   e={'routes':checks,'page_console_errors':errs};e['passed']=all(x['status']==200 and x['first_paint_tool_count']>0 and x['settled_tool_count']>0 for x in checks) and not errs;OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
