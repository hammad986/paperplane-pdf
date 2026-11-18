from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id248-') as temp:
 app,base,identity=helper.start_server(Path(temp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  rounds=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/pricing',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#mobile-view-pill')?.textContent.trim()==='Pricing'",timeout=15000)
    d=page.locator('#mobile-view-pill').evaluate("e=>{const r=e.getBoundingClientRect();return {text:e.textContent.trim(),left:r.left,right:r.right,width:r.width,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,viewport:innerWidth}}")
    assert d['text']=='Pricing' and d['right']<=d['viewport'] and d['scrollWidth']<=d['clientWidth'] and not errors,(d,errors)
    page.screenshot(path=str(OUT/f'id248-pricing-pill-round{n}.png'));rounds.append({'round':n,'pill':d,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id248-pricing-pill.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
