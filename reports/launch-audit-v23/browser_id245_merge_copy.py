from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id245-') as temp:
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
    page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('.seo-lede')?.textContent.includes('Files are merged in the order you add them')",timeout=15000)
    lead=page.locator('.seo-lede').inner_text();steps=page.locator('.seo-howto-step h3').all_text_contents();faqs=page.locator('.seo-faq').text_content()
    assert 'thumbnail' not in lead.lower() and 'rearrange thumbnails' not in ' '.join(steps).lower() and 'remove files and add them again' in faqs.lower() and not errors,(lead,steps,faqs,errors)
    page.screenshot(path=str(OUT/f'id245-merge-copy-round{n}.png'));rounds.append({'round':n,'lead':lead,'steps':steps,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id245-merge-copy.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
