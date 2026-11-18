from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id164-') as td:
 tmp=Path(td);pdf=tmp/'signature-source.pdf'
 with fitz.open() as d:
  p=d.new_page();p.insert_text((72,72),'SIGNATURE-PERSISTENCE-SOURCE');d.save(pdf)
 app,base,_=h.start_server(tmp/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errs=[];dialogs=[];page.on('pageerror',lambda e:errs.append(str(e)));page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf));page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='1'&&document.querySelector('#studio-loading-overlay')?.hidden===true");page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'");draw=page.locator('#pdf-draw-canvas');page.locator('#tool-sig-btn').click();draw.click(position={'x':110,'y':130});page.locator('#editor-signature-modal').wait_for(state='visible');page.locator('#sig-tab-type').click();page.locator('#editor-sig-type-input').fill('Test Signature');page.locator('#editor-sig-place-btn').click();page.wait_for_function("document.querySelector('#editor-signature-modal').hidden===true");draw.click(position={'x':140,'y':170});page.wait_for_function("window.PaperplaneEditor?.editorState?.dirty===true");annotation_count=page.evaluate("window.PaperplaneEditor.editorState.getObjects(1).filter(x=>x.type==='signature').length");assert annotation_count==1
    def on_dialog(d):dialogs.append({'type':d.type,'message':d.message});d.accept()
    page.once('dialog',on_dialog);page.reload(wait_until='domcontentloaded',timeout=30000);page.wait_for_timeout(1000);persisted_count=page.evaluate("window.PaperplaneEditor?.editorState?.getObjects(1).filter(x=>x.type==='signature').length||0");rounds.append({'round':n,'signature_before_reload':annotation_count,'beforeunload_dialogs':dialogs,'signature_after_reload':persisted_count,'page_errors':errs});assert dialogs and persisted_count==0 and not errs;c.close()
   result={'rounds':rounds};(OUT/'browser-id164-signature-beforeunload.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
