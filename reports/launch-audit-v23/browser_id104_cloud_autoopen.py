from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id104-') as temp:
 root=Path(temp);pdf=root/'cloud-modal-check.pdf'
 with fitz.open() as d:d.new_page().insert_text((72,72),'Local upload must not open Cloud Import.');d.save(pdf)
 app,base,_=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    ctx=browser.new_context(viewport={'width':1366,'height':900});page=ctx.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
    rows=[]
    for route in ('/compress-pdf','/pdf-to-text'):
     page.goto(base+route,wait_until='domcontentloaded');page.wait_for_timeout(300)
     page.locator('#file-input').set_input_files(str(pdf));page.wait_for_timeout(1200)
     row={'route':route,'cloud_modal_hidden':page.locator('#cloud-modal').evaluate("e=>e.hidden"),'selected_filename_visible':'cloud-modal-check.pdf' in page.locator('#file-list').inner_text() if page.locator('#file-list').count() else False,'page_errors':errs[:]} 
     page.screenshot(path=str(OUT/f'id104-{route[1:].replace("-","_")}-round{n}.png'));rows.append(row);assert row['cloud_modal_hidden'] and row['selected_filename_visible']
    rounds.append({'round':n,'routes':rows});ctx.close()
   result={'rounds':rounds};(OUT/'browser-id104-cloud-import-auto-open.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
