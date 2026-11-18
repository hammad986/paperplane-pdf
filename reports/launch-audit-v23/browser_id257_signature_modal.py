from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time,fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id257-') as temp:
 pdf=Path(temp)/'signature.pdf'
 with fitz.open() as doc: doc.new_page();doc.save(pdf)
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
    page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf));page.wait_for_function("document.body.classList.contains('studio-active')",timeout=15000);page.locator('#btn-more-tools-trigger').click();page.locator('#studio-sign-btn').click()
    page.wait_for_function("!document.querySelector('#digital-sign-modal').hidden",timeout=10000)
    path=page.evaluate('location.pathname');modal=page.locator('#digital-sign-modal').is_visible()
    assert path=='/studio' and modal and not errors,(path,modal,errors)
    page.screenshot(path=str(OUT/f'id257-signature-modal-round{n}.png'));rounds.append({'round':n,'path':path,'modal_visible':modal,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id257-signature-modal.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
