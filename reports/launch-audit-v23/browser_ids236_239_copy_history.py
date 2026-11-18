from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-236-239-') as temp:
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
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#file-hint')?.textContent.includes('PDF files per run')",timeout=15000)
    hint=page.locator('#file-hint').text_content().strip()
    assert 'Merge supports up to 100 PDF files per run' in hint and 'PDF file per run' not in hint,(hint,errors)
    page.goto(base+'/history',wait_until='domcontentloaded');page.wait_for_selector('#view-history:not([hidden])')
    history=page.locator('#view-history').inner_text();footer=page.locator('footer a[href="/history"]').text_content()
    assert 'no saved history' in history.lower() and 'does not keep a job or download history list' in history and footer.strip()=='Temporary results',(history,footer,errors)
    page.screenshot(path=str(OUT/f'id236-239-history-round{n}.png'));rounds.append({'round':n,'merge_accessible_hint':hint,'history_heading':page.locator('#view-history h1').inner_text(),'footer_link':footer,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-ids236-239-copy-history.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
