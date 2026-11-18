from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id254-') as temp:
 app,base,identity=helper.start_server(Path(temp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  token=identity['accounts'][1][1];rounds=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}]);page.goto(base+'/html-to-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
    page.locator('#url').fill('http://127.0.0.1:8000/private');page.locator('#run-button').click()
    page.wait_for_timeout(12000)

    txt=page.locator('#view-tool-desk').inner_text()
    assert 'security guard' in txt.lower() and "access to host '127.0.0.1' is forbidden" in txt.lower(),txt
    assert 'not pasted HTML snippets' in page.locator('.seo-lede').inner_text() and not errors,(txt,errors)
    page.screenshot(path=str(OUT/f'id254-html-url-round{n}.png'));rounds.append({'round':n,'private_url_error_excerpt':txt[-600:],'seo_copy':page.locator('.seo-lede').inner_text(),'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id254-html-url.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
