from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id158-') as td:
 tmp=Path(td);app,base,_=h.start_server(tmp/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  files=[]
  for i,text in enumerate(('FIRST-ROUND-A','FIRST-ROUND-B','SECOND-ROUND-A','SECOND-ROUND-B')):
   f=tmp/f'{i}.pdf';c=canvas.Canvas(str(f),pagesize=(300,300));c.drawString(30,150,text);c.save();files.append(f)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));page.goto(base+'/merge-pdf',wait_until='domcontentloaded');results=[]
    for k,pair in enumerate((files[:2],files[2:])):
     page.locator('#file-input').set_input_files([str(x) for x in pair]);page.locator('#run-button').click();page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden",timeout=30000)
     with page.expect_download(timeout=30000) as ev:page.locator('#result-download-link').click()
     pdf=PdfReader(ev.value.path());txt='\n'.join(pg.extract_text() or '' for pg in pdf.pages);assert len(pdf.pages)==2 and pair[0].stem not in txt or len(pdf.pages)==2
     markerA='FIRST-ROUND' if k==0 else 'SECOND-ROUND';assert txt.count(markerA)==2,txt
     results.append({'filename':ev.value.suggested_filename,'pages':len(pdf.pages),'markers':txt})
     if k==0:
      assert page.locator('#result-restart-btn').inner_text().strip()=='Process Another File'
      page.locator('#result-restart-btn').click();page.wait_for_timeout(100);assert page.locator('#result').is_hidden() and page.locator('#file-list').inner_text().strip()==''
      assert page.url.endswith('/merge-pdf')
    page.screenshot(path=str(OUT/f'id158-process-another-round{n}.png'));item={'round':n,'url_after_restart':page.url,'first_and_second_results':results,'file_list_empty_after_restart':True,'result_hidden_after_restart':True,'page_errors':errs};assert not errs;rounds.append(item);c.close()
   res={'rounds':rounds};(OUT/'browser-id158-process-another-workflow.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
