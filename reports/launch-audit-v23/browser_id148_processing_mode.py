from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id148-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));observed=[]
    for route in ('/merge-pdf','/split-pdf'):
     resp=page.goto(base+route,wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#client-privacy-toggle')")
     checkbox=page.locator('#client-privacy-toggle');observed.append({'route':route,'status':resp.status,'checked':checkbox.is_checked(),'localStorage':page.evaluate("()=>localStorage.getItem('paperplane-pdf-processing-mode')")})
    page.locator('label.toggle-switch-sm:has(#client-privacy-toggle)').click();observed.append({'action':'select_server_mode','checked':page.locator('#client-privacy-toggle').is_checked(),'localStorage':page.evaluate("()=>localStorage.getItem('paperplane-pdf-processing-mode')")})
    page.goto(base+'/rotate-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#client-privacy-toggle')")
    observed.append({'route':'/rotate-pdf_after_server_choice','checked':page.locator('#client-privacy-toggle').is_checked(),'localStorage':page.evaluate("()=>localStorage.getItem('paperplane-pdf-processing-mode')")})
    page.goto(base+'/settings',wait_until='domcontentloaded');page.locator('#sidebar-settings-gear-btn').click();page.locator('#settings-tab-btn-privacy').click();observed.append({'route':'settings-privacy','checked':page.locator('#settings-client-privacy-toggle').is_checked(),'localStorage':page.evaluate("()=>localStorage.getItem('paperplane-pdf-processing-mode')")});page.locator('label.toggle-switch-sm:has(#settings-client-privacy-toggle)').click()
    page.goto(base+'/remove-pages-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#client-privacy-toggle')");observed.append({'route':'/remove-pages-pdf_after_local_choice','checked':page.locator('#client-privacy-toggle').is_checked(),'localStorage':page.evaluate("()=>localStorage.getItem('paperplane-pdf-processing-mode')")})
    assert observed[0]['checked'] is True and observed[1]['checked'] is True and observed[2]['checked'] is False and observed[2]['localStorage']=='server' and observed[3]['checked'] is False and observed[4]['checked'] is False and observed[5]['checked'] is True and observed[5]['localStorage']=='local' and not errors
    page.screenshot(path=str(OUT/f'id148-processing-mode-round{n}.png'));rounds.append({'round':n,'observations':observed,'page_errors':errors});c.close()
   result={'rounds':rounds};(OUT/'browser-id148-processing-mode-persistence.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
