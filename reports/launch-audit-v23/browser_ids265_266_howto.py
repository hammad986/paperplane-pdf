from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-265-266-') as temp:
 app,base,identity=helper.start_server(Path(temp)/'data')
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
    for width,height in ((1366,900),(390,844),(320,760)):
     page=browser.new_page(viewport={'width':width,'height':height});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(base+'/ai-intelligence',wait_until='domcontentloaded');page.wait_for_selector('#view-ai-studio:not([hidden])')
     ai=page.locator('.ai-howto-section');assert ai.is_visible()
     ai_data={'heading':ai.locator('h2').inner_text(),'steps':ai.locator('li').all_text_contents(),'scroll_width':page.locator('body').evaluate('e=>e.scrollWidth'),'viewport':width}
     assert len(ai_data['steps'])==3 and 'general question' in ' '.join(ai_data['steps']).lower() and ai_data['scroll_width']<=width,ai_data
     page.screenshot(path=str(OUT/f'id265-ai-howto-{width}-round{n}.png'))
     page.goto(base+'/download',wait_until='domcontentloaded');page.wait_for_selector('#view-download:not([hidden])')
     section=page.locator('.download-howto-section');dl_steps=section.locator('.seo-howto-step').all_text_contents();hero=page.locator('.download-hero-text').inner_text()
     dl_data={'heading':section.locator('#download-howto-title').inner_text(),'hero':hero,'steps':dl_steps,'scroll_width':page.locator('body').evaluate('e=>e.scrollWidth'),'viewport':width}
     assert len(dl_steps)==3 and 'No app installer is available' in ' '.join(dl_steps) and 'browser-based PDF tools' in hero and dl_data['scroll_width']<=width, (dl_data,page.evaluate("[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,id:e.id,cls:String(e.className).slice(0,70),left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width,scroll:e.scrollWidth,client:e.clientWidth})).filter(e=>e.left>=0&&e.right>innerWidth+1).slice(0,30)"))
     assert not errors,errors
     page.screenshot(path=str(OUT/f'id266-download-howto-{width}-round{n}.png'))
     rounds.append({'round':n,'viewport':width,'ai':ai_data,'apps':dl_data,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-ids265-266-howto.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
