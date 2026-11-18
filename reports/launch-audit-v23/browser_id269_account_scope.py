from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time,fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id269-') as temp:
 root=Path(temp);pdf=root/'account-a-private.pdf'
 with fitz.open() as doc:
  page=doc.new_page();page.insert_text((72,72),'ACCOUNT A ONLY MARKER');doc.save(pdf)
 app,base,identity=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  rounds=[];tokens=[x[1] for x in identity['accounts']]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    context=browser.new_context(viewport={'width':1366,'height':900});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    context.add_cookies([{'name':'paperplane_token','value':tokens[0],'url':base,'httpOnly':True}])
    page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf));page.wait_for_function("document.querySelector('#studio-page-count')?.textContent.trim()==='1' && document.querySelector('#studio-canvas-area canvas')",timeout=20000)
    page.wait_for_timeout(600)
    context.clear_cookies();context.add_cookies([{'name':'paperplane_token','value':tokens[1],'url':base,'httpOnly':True}])
    page.goto(base+'/studio',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=15000);page.wait_for_timeout(1000)
    state=page.evaluate("({count:document.querySelector('#studio-page-count')?.textContent.trim(),name:document.querySelector('#studio-document-name')?.textContent||'',empty:!!document.querySelector('#studio-canvas-area .studio-empty-state')})")
    assert state['count']=='0' and state['empty'] and 'account-a' not in state['name'].lower() and not errors,(state,errors)
    page.screenshot(path=str(OUT/f'id269-account-scope-round{n}.png'));rounds.append({'round':n,'new_account_studio':state,'page_errors':errors});context.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id269-account-scope.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
