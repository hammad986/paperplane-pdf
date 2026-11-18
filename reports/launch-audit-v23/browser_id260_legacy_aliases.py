from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
aliases={'/resize-photo':'/resize-image-dimensions','/photo-resize':'/resize-image-dimensions','/compress-photo':'/compress-image-online','/add-page-numbers':'/add-page-numbers-to-pdf'}
with TemporaryDirectory(prefix='paperplane-id260-') as temp:
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
    checks=[]
    for old,target in aliases.items():
     response=page.goto(base+old,wait_until='domcontentloaded');assert page.url.endswith(target) and response.status==200,(old,page.url,response.status)
     checks.append({'legacy_path':old,'canonical_path':target,'final_status':response.status})
    page.goto(base+'/',wait_until='domcontentloaded');links=page.locator('a[href]').evaluate_all("els=>els.map(e=>e.getAttribute('href'))")
    broken=[old for old in aliases if old in links]
    assert not broken and not errors,(broken,errors)
    page.screenshot(path=str(OUT/f'id260-legacy-aliases-round{n}.png'));rounds.append({'round':n,'redirects':checks,'obsolete_home_links':broken,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id260-legacy-aliases.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
