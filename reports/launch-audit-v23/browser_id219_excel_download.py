from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';fixture=ROOT/'reports'/'launch-audit-v5'/'catalog-samples'/'audit-office.xlsx'
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id219-') as tmp:
 app,base,_=helper.start_server(Path(tmp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  results=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/excel-to-pdf',wait_until='domcontentloaded');page.locator('#file-input').set_input_files(str(fixture));page.wait_for_function("!document.querySelector('#run-button').disabled")
    page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
    with page.expect_download(timeout=30000) as ev:page.locator('#result-download-link').click()
    dl=ev.value;target=OUT/f'id219-excel-output-round{n}.pdf';dl.save_as(str(target))
    with fitz.open(target) as doc:
     text='\n'.join(x.get_text() for x in doc);count=doc.page_count
    assert count>=1 and 'AUDIT_OFFICE_EXCEL_OUTPUT' in text,text[:500]
    assert len(text)>100,(count,len(text));assert not errors,errors
    results.append({'round':n,'filename':dl.suggested_filename,'pages':count,'bytes':target.stat().st_size,'text_chars':len(text),'marker_present':True,'page_errors':errors});page.close()
   browser.close()
  (OUT/'browser-id219-excel-download.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
 finally:app.terminate();app.wait(timeout=5)
