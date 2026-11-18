from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id126-') as temp:
 root=Path(temp);pdf=root/'audit.pdf'
 with fitz.open() as d:d.new_page().insert_text((72,72),'Security modal entry point check.');d.save(pdf)
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
    ctx=browser.new_context(viewport={'width':1366,'height':900});page=ctx.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));routes=[]
    for route in ('/protect-pdf','/unlock-pdf'):
     page.goto(base+route,wait_until='domcontentloaded');page.wait_for_selector('#file-input',state='attached');page.locator('#file-input').set_input_files(str(pdf));page.wait_for_timeout(500)
     trigger=page.locator('#open-security-audit-tool-btn');exists=trigger.count()==1;trigger.click();modal=page.locator('#security-modal');page.wait_for_function("document.querySelector('#security-modal')?.hidden===false")
     active=page.locator('#sec-tab-audit').evaluate("e=>e.classList.contains('active') || e.getAttribute('aria-selected')==='true'")
     content=page.locator('#security-modal').inner_text();valid=modal.is_visible() and 'Security Audit & Sanitize' in content
     current_name=page.evaluate("()=>window.PaperplaneSecurityForms?.currentFile?.name||''")
     page.screenshot(path=str(OUT/f'id126-{route[1:]}-round{n}.png'));routes.append({'route':route,'entry_button_visible':exists,'modal_visible':valid,'audit_tab_active':active,'security_controller_received_uploaded_file':current_name==pdf.name,'current_file_name':current_name,'page_errors':errs[:]});assert exists and valid and active and current_name==pdf.name and not errs
     page.locator('#security-modal').evaluate("e=>e.hidden=true")
    rounds.append({'round':n,'routes':routes});ctx.close()
   result={'rounds':rounds};(OUT/'browser-id126-security-entrypoints.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
