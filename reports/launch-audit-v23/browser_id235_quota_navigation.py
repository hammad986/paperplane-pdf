from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id235-') as temp:
 app,base,identity=helper.start_server(Path(temp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  token=identity['accounts'][1][1]; rounds=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
    checks=[]
    for route in ('/merge-pdf','/rotate-pdf','/compress-pdf','/split-pdf','/merge-pdf'):
     page.goto(base+route,wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#quota-text')?.textContent.trim() !== 'Checking usage…'",timeout=15000)
     checks.append({'route':route,'text':page.locator('#quota-text').inner_text()})
    assert all(x['text']!='Checking usage…' for x in checks) and not errors,(checks,errors)
    page.screenshot(path=str(OUT/f'id235-quota-navigation-round{n}.png'));rounds.append({'round':n,'checks':checks,'page_errors':errors});page.close()
   browser.close()
  out={'rounds':rounds};(OUT/'browser-id235-quota-navigation.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
 finally:app.terminate();app.wait(timeout=5)
