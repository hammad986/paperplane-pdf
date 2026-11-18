from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id176-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_selector('#sidebar-tools-container button[data-select-operation="rotate"]');page.evaluate("showToast('stale audit toast','info',10000)");assert page.locator('.toast-notice').count()==1;before=page.locator('#crumb-tool').inner_text();page.locator('#sidebar-tools-container button[data-select-operation="rotate"]').click();page.wait_for_function("location.pathname==='/rotate-pdf' && document.querySelector('#crumb-tool')?.textContent.trim()==='Rotate PDF'");toast_count=page.locator('.toast-notice').count();after=page.locator('#crumb-tool').inner_text();assert toast_count==0 and before=='Merge PDF' and after=='Rotate PDF' and not errors
    page.screenshot(path=str(OUT/f'id176-navigation-toast-breadcrumb-round{n}.png'));rounds.append({'round':n,'before_breadcrumb':before,'after_breadcrumb':after,'toast_after_navigation':toast_count,'url':page.url,'page_errors':errors});c.close()
   result={'rounds':rounds};(OUT/'browser-id176-toast-breadcrumb-navigation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
