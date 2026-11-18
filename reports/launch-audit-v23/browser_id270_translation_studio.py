from pathlib import Path
from tempfile import TemporaryDirectory
import base64,json,socket,sys,time,fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id270-') as temp:
 root=Path(temp);pdf=root/'translated.pdf'
 with fitz.open() as doc:
  page=doc.new_page();page.insert_text((72,72),'Hindi translated result fixture');doc.save(pdf)
 payload=base64.b64encode(pdf.read_bytes()).decode();app,base,identity=helper.start_server(root/'data')
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
    page.goto(base+'/translate-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
    page.evaluate("async b64=>{const raw=atob(b64);const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));renderTranslationResult(new Blob([bytes],{type:'application/pdf'}),'fixture_translated.pdf','hi',100,0,'translated')}",payload)
    button=page.locator('#translation-view-studio-btn');assert button.is_visible() and page.locator('#result-content a[download="fixture_translated.pdf"]').is_visible()
    button.click();page.wait_for_function("location.pathname==='/studio' && document.querySelector('#studio-page-count')?.textContent.trim()==='1'",timeout=20000)
    canvases=page.locator('#studio-canvas-area canvas').count();assert canvases>0 and not errors,(canvases,errors)
    page.screenshot(path=str(OUT/f'id270-translation-studio-round{n}.png'));rounds.append({'round':n,'path':page.evaluate('location.pathname'),'pages':page.locator('#studio-page-count').text_content(),'rendered_canvas_count':canvases,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id270-translation-studio.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
