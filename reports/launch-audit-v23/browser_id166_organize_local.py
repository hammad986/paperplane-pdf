from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id166-') as td:
 tmp=Path(td);app,base,_=h.start_server(tmp/'db');source=tmp/'organize.pdf';cv=canvas.Canvas(str(source),pagesize=(300,300))
 for marker in ('ORDER-ONE','ORDER-TWO','ORDER-THREE'):
  cv.drawString(30,150,marker);cv.showPage()
 cv.save()
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=c.new_page();errs=[];jobs=[];page.on('pageerror',lambda e:errs.append(str(e)));page.on('request',lambda r:jobs.append(r.url) if '/api/jobs' in r.url else None);resp=page.goto(base+'/organize-pdf',wait_until='domcontentloaded');page.wait_for_selector('#pages');local=page.locator('#client-privacy-toggle').is_checked();page.locator('#pages').fill('3,1,2');page.locator('#file-input').set_input_files(str(source));assert page.locator('#pages').input_value()=='3,1,2';page.locator('#run-button').click();page.wait_for_function("document.querySelector('#result')&&!document.querySelector('#result').hidden",timeout=30000)
    with page.expect_download(timeout=30000) as ev:page.locator('#result-download-link').click()
    pdf=PdfReader(ev.value.path());markers=[(pg.extract_text() or '').strip() for pg in pdf.pages];assert markers==['ORDER-THREE','ORDER-ONE','ORDER-TWO'],markers;assert not jobs,jobs;page.screenshot(path=str(OUT/f'id166-organize-local-round{n}.png'));assert not errs;rounds.append({'round':n,'status':resp.status,'local_toggle':local,'output_pages':markers,'api_jobs_requests':jobs,'page_errors':errs});c.close()
   result={'rounds':rounds};(OUT/'browser-id166-organize-client-side.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
