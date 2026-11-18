from pathlib import Path
from tempfile import TemporaryDirectory
import json,random,socket,sys,time
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id255-') as temp:
 root=Path(temp);source=root/'default-100kb.jpg';Image.frombytes('RGB',(1200,900),random.Random(20261117).randbytes(1200*900*3)).save(source,'JPEG',quality=52,optimize=True)
 app,base,identity=helper.start_server(root/'data')
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
    page.context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}]);page.goto(base+'/compress-image-online',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
    default=page.locator('#target_kb').input_value();assert default=='100',default
    page.locator('#file-input').set_input_files(str(source));page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
    with page.expect_download(timeout=15000) as evt:page.locator('#result-download-link').click()
    out=root/f'default-round{n}.jpg';evt.value.save_as(out)
    with Image.open(out) as img:img.verify()
    size=out.stat().st_size;assert 0<size<=100*1024 and not errors,(size,errors)
    page.screenshot(path=str(OUT/f'id255-default-target-round{n}.png'));rounds.append({'round':n,'shown_default_kb':default,'output_bytes':size,'under_target':True,'page_errors':errors});page.close()
   browser.close()
  result={'rounds':rounds};(OUT/'browser-id255-default-photo-target.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 finally:app.terminate();app.wait(timeout=5)
