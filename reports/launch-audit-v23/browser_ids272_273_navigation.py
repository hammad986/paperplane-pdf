from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time,fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-272-273-') as temp:
 root=Path(temp);pdf=root/'temporary-upload.pdf'
 with fitz.open() as doc:
  pg=doc.new_page();pg.insert_text((72,72),'TEMPORARY UPLOAD MARKER');doc.save(pdf)
 app,base,identity=helper.start_server(root/'data')
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
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.locator('#file-input').set_input_files(str(pdf));page.wait_for_function("document.querySelectorAll('#file-list .file-row-card').length===1")
    page.goto(base+'/rotate-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending') && document.querySelector('#view-tool-desk:not([hidden])')")
    notices=page.locator('.toast-notice').all_text_contents();assert not any('temporary tool uploads' in t.lower() for t in notices) and any('temporary-upload.pdf' in t.lower() for t in notices),notices
    page.locator('#sidebar [data-select-operation="split"]').click();page.wait_for_function("state.operation==='split'")
    page.wait_for_timeout(250);after_navigation=page.locator('.toast-notice').all_text_contents()
    assert not any('temporary' in t.lower() for t in after_navigation),after_navigation
    page.evaluate("sessionStorage.setItem('paperplane-active-view','studio')")
    page.goto(base+'/',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')");page.wait_for_timeout(1000)
    landing=page.evaluate("({path:location.pathname,active:state.activeView,studioVisible:!document.querySelector('#view-pdf-studio').hidden})")
    assert landing['studioVisible'] is False and landing['active']=='tool-desk' and landing['path']=='/',(landing,notices,errors)
    assert not errors,errors
    page.screenshot(path=str(OUT/f'id272-273-reload-round{n}.png'));rounds.append({'round':n,'post_upload_notices':notices,'after_tool_navigation_notices':after_navigation,'root_load':landing,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-ids272-273-navigation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
