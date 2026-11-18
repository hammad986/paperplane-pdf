from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id230-') as tmp:
 app,base,identities=helper.start_server(Path(tmp)/'data')
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
    context=browser.new_context(viewport={'width':1366,'height':900});email,token=identities['accounts'][0];context.add_cookies([{'name':'paperplane_token','value':token,'url':base}]);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    views=[]
    for route in ('/pricing','/terms','/settings'):
     response=page.goto(base+route,wait_until='domcontentloaded');assert response.status==200
     if route=='/settings':
      page.wait_for_function("document.querySelector('#settings-user-email')?.textContent.includes('audit-')",timeout=10000)
      page.locator('#settings-tab-btn-billing').click();page.wait_for_timeout(200)
     txt=' '.join(page.locator('body').inner_text().split()).casefold()
     banned=[x for x in ('all plans are billed monthly','renew automatically unless cancelled','renew on 14 dec 2026') if x in txt]
     assert not banned,(route,banned)
     if route=='/pricing': assert 'one-time' in txt or 'zero recurring charge' in txt,txt[:400]
     views.append({'route':route,'no_auto_renew_contradiction':True,'one_time_claim_present':('one-time' in txt or 'zero recurring charge' in txt)})
    assert not errors,errors;results.append({'round':n,'views':views,'page_errors':errors});context.close()
   browser.close()
  (OUT/'browser-id230-renewal-copy.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
 finally:app.terminate();app.wait(timeout=5)
