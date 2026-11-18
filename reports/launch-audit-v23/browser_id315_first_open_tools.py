from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

def fixture(path):
 with fitz.open() as d:
  p=d.new_page();p.insert_text((72,72),'Fresh first-open Studio tool activation fixture.');d.save(path)
with TemporaryDirectory(prefix='paperplane-id315-') as temp:
 root=Path(temp);pdf=root/'first-open-tool-fixture.pdf';fixture(pdf)
 app,base,identity=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  outcomes=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for round_no in (1,2):
    context=browser.new_context(viewport={'width':1366,'height':900})
    page=context.new_page();errors=[];console_errors=[];auth_401=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None)
    page.on('response',lambda response:auth_401.append(response.url) if response.status==401 else None)
    page.goto(base+'/studio',wait_until='domcontentloaded')
    page.locator('#studio-file-input').set_input_files(str(pdf))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1' && document.querySelector('#studio-loading-overlay')?.hidden === true",timeout=20000)
    page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'",timeout=15000)
    page.locator('#tool-text-btn').click()
    text_active=page.locator('#tool-text-btn').evaluate("el=>el.classList.contains('active')")
    edit_canvas=page.locator('#pdf-draw-canvas')
    edit_canvas.wait_for(state='visible',timeout=5000)
    edit_canvas.click(position={'x':80,'y':80})
    page.locator('#editor-text-panel').wait_for(state='visible',timeout=5000)
    page.locator('#editor-cancel-text-btn').click()
    page.locator('#tool-stamp-btn').click()
    edit_canvas.click(position={'x':120,'y':150})
    page.locator('#editor-stamp-picker').wait_for(state='visible',timeout=5000)
    unexpected_console_errors=[message for message in console_errors if '401 (Unauthorized)' not in message]
    outcome={'round':round_no,'first_open_without_reload':True,'text_panel_visible':True,'text_tool_active':text_active,'stamp_picker_visible':True,'page_errors':errors,'expected_guest_auth_401_urls':auth_401,'unexpected_console_errors':unexpected_console_errors}
    outcomes.append(outcome)
    page.screenshot(path=str(OUT/f'id315-first-open-tools-round{round_no}.png'))
    context.close()
   browser.close()
  result={'base':base,'rounds':outcomes}
  (OUT/'browser-id315-first-open-tools.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
  print(json.dumps(result,indent=2))
  assert len(outcomes)==2 and all(x['text_tool_active'] and x['stamp_picker_visible'] and not x['page_errors'] and not x['unexpected_console_errors'] for x in outcomes)
 finally:
  app.terminate();app.wait(timeout=5)
