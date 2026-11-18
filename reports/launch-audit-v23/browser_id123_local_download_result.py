from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id123-') as temp:
 root=Path(temp);src=[]
 for n,text in ((1,'FIRST SOURCE MARKER'),(2,'SECOND SOURCE MARKER')):
  f=root/f'source-{n}.pdf'
  with fitz.open() as d:d.new_page().insert_text((72,72),text);d.save(f)
  src.append(f)
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
    ctx=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=ctx.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_selector('#run-button')
    page.locator('#file-input').set_input_files([str(x) for x in src]);page.wait_for_function("!document.querySelector('#run-button').disabled")
    assert page.evaluate("()=>localStorage.getItem('paperplane-pdf-processing-mode')")!='server'
    page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
    with page.expect_download(timeout=30000) as event:page.locator('#result-download-link').click()
    download=event.value;path=root/f'download-round{n}.pdf';download.save_as(str(path))
    with fitz.open(path) as out:
     extracted='\n'.join(pg.get_text() for pg in out);pages=len(out)
    meta=page.locator('#result-meta').inner_text();visible=page.locator('#result-download-link').is_visible();size_text=meta.split('·')[-1].strip()
    page.screenshot(path=str(OUT/f'id123-local-merge-round{n}.png'))
    assert pages==2 and 'FIRST SOURCE MARKER' in extracted and 'SECOND SOURCE MARKER' in extracted and visible and ('KiB' in size_text or ' B' in size_text)
    item={'round':n,'download_name':download.suggested_filename,'download_bytes':path.stat().st_size,'pdf_pages':pages,'content_markers_present':all(x in extracted for x in ('FIRST SOURCE MARKER','SECOND SOURCE MARKER')),'result_meta':meta,'download_link_visible':visible,'page_errors':errs}
    rounds.append(item);ctx.close()
   result={'rounds':rounds};(OUT/'browser-id123-local-download-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
