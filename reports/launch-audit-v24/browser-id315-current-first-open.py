from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent
with TemporaryDirectory(prefix='paperplane-id315-current-') as temp:
 root=Path(temp); pdf=root/'first-open-69-pages.pdf'
 with fitz.open() as doc:
  for n in range(1,70):
   pg=doc.new_page(); pg.insert_text((72,72),f'Current v233 first-open page {n}')
  doc.save(pdf)
 app,base,_=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
   except OSError: time.sleep(.15)
  rounds=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for no in (1,2):
    context=browser.new_context(viewport={'width':1366,'height':900}); page=context.new_page(); errors=[]; console=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:console.append(m.text) if m.type=='error' and '401 (Unauthorized)' not in m.text else None)
    page.goto(base+'/studio',wait_until='domcontentloaded')
    asset=page.locator('script[src*="app.js"]').get_attribute('src')
    page.locator('#studio-file-input').set_input_files(str(pdf))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=30000)
    page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
    page.locator('#tool-text-btn').click(); text_active=page.locator('#tool-text-btn').evaluate("e=>e.classList.contains('active')")
    canvas=page.locator('#pdf-draw-canvas'); canvas.click(position={'x':80,'y':80}); page.locator('#editor-text-panel').wait_for(state='visible',timeout=7000)
    page.locator('#editor-cancel-text-btn').click(); page.locator('#tool-stamp-btn').click(); canvas.click(position={'x':120,'y':150}); page.locator('#editor-stamp-picker').wait_for(state='visible',timeout=7000)
    row={'round':no,'app_asset':asset,'loaded_pages':69,'reload_after_open':False,'text_panel_visible':True,'text_tool_active':text_active,'stamp_picker_visible':True,'page_errors':errors,'console_errors':console}
    rounds.append(row); page.screenshot(path=str(OUT/f'browser-id315-current-first-open-round{no}.png')); context.close()
   browser.close()
  result={'rounds':rounds}; (OUT/'browser-id315-current-first-open.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
  assert len(rounds)==2 and all(x['app_asset']=='/assets/app.js?v=233' and x['loaded_pages']==69 and x['text_panel_visible'] and x['stamp_picker_visible'] and not x['page_errors'] and not x['console_errors'] for x in rounds)
 finally:
  app.terminate(); app.wait(timeout=5)
