from pathlib import Path
from tempfile import TemporaryDirectory
import json,sys,socket,time
import os
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'/'launch-audit-v23'
ROUND=int(os.environ.get('ID45_ROUND','1'))
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id45-layout-') as temp:
 root=Path(temp);fixture=root/'studio-layout.pdf'
 with fitz.open() as doc:
  doc.new_page().insert_text((72,72),'ID45 Studio layout fixture')
  doc.save(fixture)
 app,base,_=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  results=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for width,height in [(320,740),(360,800),(390,844),(820,1180),(1024,768),(1104,760),(1366,900),(1920,1080)]:
    page=browser.new_page(viewport={'width':width,'height':height},is_mobile=width<500,has_touch=width<500)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    response=page.goto(base+'/studio',wait_until='domcontentloaded')
    page.locator('#studio-file-input').set_input_files(str(fixture))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim() === '1' && document.querySelector('#studio-loading-overlay')?.hidden === true",timeout=20000)
    start=page.evaluate("""()=>({footerHidden:getComputedStyle(document.querySelector('.app-global-footer')).visibility==='hidden',noticeCount:document.querySelectorAll('.ephemeral-work-notice').length,bannerPresent:document.body.innerText.includes('PDF and page edits save here'),toolbar:document.querySelector('#studio-toolbar').getBoundingClientRect().height,docWidth:document.documentElement.scrollWidth,viewport:innerWidth,saveVisible:!!(document.querySelector('#save-studio-btn').getBoundingClientRect().width),footerY:document.querySelector('.app-global-footer').getBoundingClientRect().y})""")
    assert response and response.status==200,response.status if response else None
    assert start['bannerPresent'] is False and start['footerHidden'] and start['docWidth']<=width and start['saveVisible'],start
    if width>=1024: assert start['toolbar']<=190,start
    if width >= 901:
     page.locator('.main-area').evaluate("element=>element.scrollTo(0,element.scrollHeight)")
    else:
     page.evaluate("window.scrollTo(0,document.body.scrollHeight)")
    page.wait_for_timeout(250)
    footer=page.evaluate("""()=>({revealed:document.documentElement.classList.contains('footer-revealed'),visibility:getComputedStyle(document.querySelector('.app-global-footer')).visibility,footerY:document.querySelector('.app-global-footer').getBoundingClientRect().y,docWidth:document.documentElement.scrollWidth})""")
    assert footer['revealed'] and footer['visibility']=='visible' and footer['docWidth']<=width,footer
    assert not errors,errors
    page.screenshot(path=str(OUT/f'id45-studio-{width}-round{ROUND}.png'))
    results.append({'viewport':[width,height],'status':response.status,'initial':start,'scrolled_footer':footer,'page_errors':errors})
    page.close()
   browser.close()
  (OUT/f'browser-id45-responsive-studio-layout-round{ROUND}.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  print(json.dumps(results,indent=2))
 finally:
  app.terminate();app.wait(timeout=5)
