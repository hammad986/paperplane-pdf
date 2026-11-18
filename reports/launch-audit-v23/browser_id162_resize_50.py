from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time,io
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id162-') as td:
 tmp=Path(td); app,base,_=h.start_server(tmp/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  src=tmp/'fixture.png';Image.new('RGB',(120,80),(40,120,180)).save(src)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));resp=page.goto(base+'/resize-image-dimensions',wait_until='domcontentloaded');page.wait_for_selector('#scale_percent');page.locator('#scale_percent').fill('50');page.locator('#file-input').set_input_files(str(src));page.wait_for_function("document.querySelector('#scale_percent')?.value === '50'");assert page.locator('#scale_percent').input_value()=='50';
    page.locator('#run-button').click();page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden",timeout=30000)
    with page.expect_download(timeout=30000) as ev: page.locator('#result-download-link').click()
    d=ev.value;raw=Path(d.path()).read_bytes();img=Image.open(io.BytesIO(raw));dim=img.size;assert dim==(60,40),dim
    page.screenshot(path=str(OUT/f'id162-resize-50-round{n}.png'));item={'round':n,'status':resp.status,'scale_value_after_upload':page.locator('#scale_percent').input_value(),'download_name':d.suggested_filename,'dimensions':dim,'bytes':len(raw),'page_errors':errs};assert resp.status==200 and not errs
    rounds.append(item);c.close()
   res={'rounds':rounds};(OUT/'browser-id162-resize-50-percent.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
