from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-263-264-') as temp:
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
    page.goto(base+'/scan-to-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('.seo-lede')?.textContent.length>10")
    scan={'description':page.locator('.tool-hero-card').inner_text(),'intro':page.locator('.seo-lede').inner_text(),'option':page.locator('#page_size').is_visible(),'deskew_claim':'deskew' in (page.locator('.tool-hero-card').inner_text()+page.locator('.seo-lede').inner_text()).lower()}
    assert scan['option'] and not scan['deskew_claim'],scan
    page.goto(base+'/jpg-to-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('.seo-lede')?.textContent.length>10")
    jpg={'intro':page.locator('.seo-lede').inner_text(),'page_size_control':page.locator('#page_size').count()>0}
    assert 'A4, Letter, or auto paper sizes' not in jpg['intro'] and not jpg['page_size_control'],jpg
    assert not errors,errors
    page.screenshot(path=str(OUT/f'id263-264-copy-round{n}.png'));rounds.append({'round':n,'scan_to_pdf':scan,'jpg_to_pdf':jpg,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-ids263-264-copy.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
