from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id139-') as temp:
 app,base,_=helper.start_server(Path(temp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);rows=[]
   for n in (1,2):
    ctx=browser.new_context(viewport={'width':1366,'height':900});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));routes=[]
    for route in ('/apps','/download','/privacy','/terms','/mask-aadhaar-card-online'):
     response=page.goto(base+route,wait_until='domcontentloaded');early=page.locator('#sidebar-tools-container .sidebar-tool-item').count();awaitable=False
     page.wait_for_timeout(1100);settled=page.locator('#sidebar-tools-container .sidebar-tool-item').count();label=page.locator('#sidebar .nav-group-title').filter(has_text='Available Tools').count()
     item={'route':route,'status':response.status if response else None,'first_paint_tool_count':early,'settled_tool_count':settled,'available_tools_label_count':label,'page_errors':errors[:]}
     routes.append(item);assert response and response.status==200 and early>0 and settled>0 and label==1
    page.screenshot(path=str(OUT/f'id139-sidebar-deep-routes-round{n}.png'));rows.append({'round':n,'routes':routes});ctx.close()
   result={'rounds':rows};(OUT/'browser-id139-sidebar-tools-deep-routes.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
