import base64,fitz,json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path.cwd(); sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as h
with TemporaryDirectory() as tmp:
 app,base,_=h.start_server(Path(tmp)/'data')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
   except OSError: time.sleep(.1)
  with fitz.open() as d: d.new_page().insert_text((72,72),'Toast positioning probe'); pdf=Path(tmp)/'p.pdf';d.save(pdf)
  payload=base64.b64encode(pdf.read_bytes()).decode()
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True); c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True); page=c.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(base+'/studio',wait_until='domcontentloaded'); page.evaluate("async b64=>{let bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));let f=new File([bytes],'probe.pdf',{type:'application/pdf'});await loadDocumentIntoStudio(f)}",payload)
   page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden===true")
   page.reload(wait_until='domcontentloaded'); page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden===true")
   toast=page.locator('.toast-notice'); toast.wait_for(state='visible'); page.set_viewport_size({'width':390,'height':844}); page.wait_for_timeout(120)
   before=page.locator('.toast-notice').evaluate("t=>({top:t.getBoundingClientRect().top,rectTop:t.style.top,var:getComputedStyle(t).getPropertyValue('--studio-toast-top'),animation:getComputedStyle(t).animationName,transform:getComputedStyle(t).transform,htmlStudio:document.documentElement.classList.contains('studio-active'),bodyStudio:document.body.classList.contains('studio-active'),toolbar:document.querySelector('.studio-toolbar').getBoundingClientRect().toJSON(),cssTop:getComputedStyle(t).top})")
   page.evaluate("dispatchEvent(new Event('resize'))");page.wait_for_timeout(100)
   after=page.locator('.toast-notice').evaluate("t=>({top:t.getBoundingClientRect().top,var:getComputedStyle(t).getPropertyValue('--studio-toast-top'),transform:getComputedStyle(t).transform,toolbar:document.querySelector('.studio-toolbar').getBoundingClientRect().toJSON(),cssTop:getComputedStyle(t).top})")
   out={'before':before,'after_resize':after,'page_errors':errors}; print(json.dumps(out,indent=2)); (ROOT/'reports/launch-audit-v23/browser-self-found-studio-toast-resize-diagnostic.json').write_text(json.dumps(out,indent=2))
   b.close()
 finally: app.terminate();app.wait(timeout=10)
