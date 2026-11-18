from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id261-') as temp:
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
    page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/',wait_until='domcontentloaded');version=page.locator('#app-version').text_content().strip()
    assert version=='Version 2.0.0' and not errors,(version,errors)
    page.screenshot(path=str(OUT/f'id261-app-version-round{n}.png'));rounds.append({'round':n,'visible_version':version,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id261-app-version.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
