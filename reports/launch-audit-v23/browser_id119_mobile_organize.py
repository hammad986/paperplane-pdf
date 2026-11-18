from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id119-') as temp:
 root=Path(temp);pdf=root/'organize-mobile.pdf'
 with fitz.open() as doc:
  for n in range(1,6):doc.new_page().insert_text((72,72),f'ID 119 page {n}')
  doc.save(pdf)
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
    ctx=browser.new_context(viewport={'width':390,'height':844});page=ctx.new_page();errs=[]
    page.on('pageerror',lambda e:errs.append(str(e)))
    page.goto(base+'/studio',wait_until='domcontentloaded')
    page.locator('#studio-file-input').set_input_files(str(pdf))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='5' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
    page.locator('#btn-mode-organize').click()
    page.wait_for_function("document.querySelector('#app-shell')?.classList.contains('studio-pages-open') && document.querySelector('#btn-mode-organize')?.classList.contains('active')")
    panel=page.locator('#studio-thumbnails-bar');rect=panel.bounding_box();thumbs=page.locator('#studio-thumbnails-container .organizer-thumb-card').count()
    drawer_open=page.locator('#app-shell').evaluate("e=>e.classList.contains('studio-pages-open')")
    visible=panel.is_visible() and rect is not None and rect['width']>0 and rect['height']>0
    page.screenshot(path=str(OUT/f'id119-organize-mobile-round{n}.png'))
    page.locator('#studio-mobile-pages-btn').click();page.wait_for_function("!document.querySelector('#app-shell')?.classList.contains('studio-pages-open')")
    closed=not panel.is_visible()
    item={'round':n,'viewport':390,'organize_active':page.locator('#btn-mode-organize').get_attribute('class'),'drawer_open_after_organize':drawer_open,'panel_visible':visible,'panel_rect':rect,'page_thumbnails':thumbs,'drawer_toggle_closes_panel':closed,'page_errors':errs}
    rounds.append(item);assert drawer_open and visible and thumbs==5 and closed and not errs
    ctx.close()
   result={'rounds':rounds};(OUT/'browser-id119-mobile-organize.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
