from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id129-') as td:
 root=Path(td);pdf=root/'sanitize.pdf'
 with fitz.open() as d:d.new_page().insert_text((72,72),'Synthetic sanitize dialog input.');d.save(pdf)
 app,base,_=h.start_server(root/'data')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rows=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));routes=[]
    for route in ('/protect-pdf','/unlock-pdf'):
     page.goto(base+route,wait_until='domcontentloaded');page.locator('#file-input').set_input_files(str(pdf));page.wait_for_timeout(350);page.locator('#open-security-audit-tool-btn').click();page.locator('#sec-tab-audit').click();pane=page.locator('#sec-pane-audit');buttons=pane.get_by_role('button',name='Sanitize Document Now');count=buttons.count();visible=buttons.first.is_visible();text=buttons.first.inner_text().strip();routes.append({'route':route,'button_count':count,'one_visible_action':visible,'label':text});assert count==1 and visible and 'Sanitize Document Now' in text
     page.screenshot(path=str(OUT/f'id129-sanitize-dialog-round{n}.png'))
    rows.append({'round':n,'routes':routes,'page_errors':errors});assert not errors;c.close()
   res={'rounds':rows};(OUT/'browser-id129-sanitize-action-count.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
