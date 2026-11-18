from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id131-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);allrounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1104,'height':760});page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));routes=[]
    for route,view,target in (('/download','#view-download','#view-download .view-header-title h2'),('/developers','#view-api-docs','#view-api-docs .api-docs-meta-grid')):
     response=page.goto(base+route,wait_until='domcontentloaded');page.wait_for_function(f"document.querySelector('{view}')?.hidden===false",timeout=12000)
     if route=='/developers':
      page.wait_for_selector('.meta-label:has-text("LIMITS & RESET")',state='visible');target_el=page.locator('.api-meta-item').filter(has_text='LIMITS & RESET')
     else:target_el=page.locator(target)
     bbox=target_el.bounding_box();sidebar=page.locator('#sidebar').bounding_box();document_width=page.evaluate('document.documentElement.scrollWidth')
     intersects=bool(bbox and sidebar and bbox['x']<sidebar['x']+sidebar['width'] and bbox['x']+bbox['width']>sidebar['x'])
     item={'route':route,'status':response.status if response else None,'target_rect':bbox,'sidebar_rect':sidebar,'target_overlaps_sidebar':intersects,'document_width':document_width,'viewport':1104,'in_viewport':bool(bbox and bbox['x']>=0 and bbox['x']+bbox['width']<=1104)}
     routes.append(item);assert response and response.status==200 and bbox and not intersects and item['in_viewport'] and document_width==1104
    page.screenshot(path=str(OUT/f'id131-1104-layout-round{n}.png'));allrounds.append({'round':n,'routes':routes,'page_errors':errs});assert not errs;c.close()
   res={'rounds':allrounds};(OUT/'browser-id131-1104-sidebar-layout.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
