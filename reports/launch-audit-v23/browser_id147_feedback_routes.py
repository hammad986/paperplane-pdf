from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id147-') as td:
 app,base,identities=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[];token=identities['accounts'][0][1]
   for n in (1,2):
    c=b.new_context(viewport={'width':390,'height':844});c.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}]);page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));views=[]
    for route in ('/tool-desk','/scan-to-pdf','/merge-pdf','/settings'):
     response=page.goto(base+route,wait_until='domcontentloaded');page.wait_for_function("window.state?.user?.user_id && document.querySelector('#pp-feedback-launcher')",timeout=15000)
     page.wait_for_function("!document.querySelector('#pp-feedback-launcher').hidden && getComputedStyle(document.querySelector('#pp-feedback-container')).display!=='none'",timeout=10000)
     item={'route':route,'status':response.status if response else None,'widget_in_dom':page.locator('#pp-feedback-container').count()==1,'launcher_visible':page.locator('#pp-feedback-launcher').is_visible(),'seen_flag':page.evaluate("()=>Object.keys(localStorage).some(k=>k.includes('feedback-seen'))")};views.append(item)
    page.screenshot(path=str(OUT/f'id147-feedback-settings-round{n}.png'))
    page.locator('#pp-feedback-dismiss').click();page.wait_for_function("document.querySelector('#pp-feedback-launcher').hidden")
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("window.state?.user?.user_id && document.querySelector('#pp-feedback-launcher')",timeout=15000);page.wait_for_timeout(300)
    after={'widget_in_dom':page.locator('#pp-feedback-container').count()==1,'launcher_hidden_after_dismiss':page.locator('#pp-feedback-launcher').evaluate('e=>e.hidden'),'dismiss_flag':page.evaluate("()=>Object.keys(localStorage).some(k=>k.includes('feedback-dismissed'))")}
    assert all(v['status']==200 and v['widget_in_dom'] and v['launcher_visible'] and v['seen_flag'] for v in views) and after['widget_in_dom'] and after['launcher_hidden_after_dismiss'] and after['dismiss_flag'] and not errors
    rounds.append({'round':n,'signed_in_views':views,'after_dismiss_and_route_change':after,'page_errors':errors});c.close()
   result={'rounds':rounds};(OUT/'browser-id147-feedback-across-routes.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
