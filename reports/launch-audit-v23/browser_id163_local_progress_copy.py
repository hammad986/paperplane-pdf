from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from pypdf import PdfWriter, PdfReader
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id163-') as td:
 tmp=Path(td);app,base,_=h.start_server(tmp/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  src=[]
  for i,label in enumerate(('LOCAL-MERGE-A','LOCAL-MERGE-B')):
   w=PdfWriter();pg=w.add_blank_page(width=300,height=300);pg.extract_text=lambda: label
   # Add searchable marker via reportlab
   from reportlab.pdfgen import canvas
   path=tmp/f'{i}.pdf';c=canvas.Canvas(str(path),pagesize=(300,300));c.drawString(30,150,label);c.save();src.append(path)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=c.new_page();page.add_init_script("""(()=>{window.__progressSnapshots=[];new MutationObserver(()=>{const xs=[1,2,3,4].map(i=>document.querySelector('#step-'+i)?.textContent.trim()||'');if(xs.some(x=>x))window.__progressSnapshots.push(xs)}).observe(document,{subtree:true,childList:true,characterData:true})})()""");errs=[];page.on('pageerror',lambda e:errs.append(str(e)));resp=page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.locator('#file-input').set_input_files([str(x) for x in src]);page.wait_for_function("document.querySelectorAll('#file-list *').length>0");assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")!='server'
    page.locator('#run-button').click();page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden",timeout=30000);snapshots=page.evaluate('window.__progressSnapshots');found=[s for s in snapshots if any('Read files locally' in x or 'Process in browser' in x or 'Prepare output' in x for x in s)];assert found, snapshots
    last=found[-1];assert any('Stream Upload' in x for s in []) is False
    with page.expect_download(timeout=30000) as ev:page.locator('#result-download-link').click()
    pdf=PdfReader(ev.value.path());text='\n'.join(pg.extract_text() or '' for pg in pdf.pages);assert len(pdf.pages)==2 and 'LOCAL-MERGE-A' in text and 'LOCAL-MERGE-B' in text
    assert not any('Stream Upload' in x for s in found for x in s),found
    page.screenshot(path=str(OUT/f'id163-local-merge-progress-round{n}.png'));record={'round':n,'status':resp.status,'mode':page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')"),'observed_progress':found,'download':ev.value.suggested_filename,'pages':len(pdf.pages),'text':text,'page_errors':errs};assert resp.status==200 and not errs;rounds.append(record);c.close()
   res={'rounds':rounds};(OUT/'browser-id163-local-merge-progress-copy.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
