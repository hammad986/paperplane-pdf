from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id253-') as temp:
 root=Path(temp);app,base,identity=helper.start_server(root/'data');image=root/'scan.jpg';Image.new('RGB',(2400,1800),(110,140,170)).save(image)
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  token=identity['accounts'][1][1];rounds=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}]);page.goto(base+'/scan-to-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
    page.locator('#page_size').select_option('original');page.locator('#file-input').set_input_files(str(image));page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=20000)
    with page.expect_download(timeout=10000) as evt:page.locator('#result-download-link').click()
    output=root/f'scan-round{n}.pdf';evt.value.save_as(output)
    with fitz.open(output) as doc:rect=doc[0].rect
    assert abs(rect.width-864)<1 and abs(rect.height-648)<1 and not errors,(rect,errors)
    page.screenshot(path=str(OUT/f'id253-scan-page-round{n}.png'));rounds.append({'round':n,'input_pixels':[2400,1800],'requested_dpi':200,'pdf_points':[rect.width,rect.height],'download':evt.value.suggested_filename,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id253-scan-dpi.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
