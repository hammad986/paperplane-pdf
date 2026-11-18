from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time,io
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id165-') as td:
 tmp=Path(td);app,base,_=h.start_server(tmp/'db');source=tmp/'photo.png';Image.new('RGB',(600,400),(180,80,60)).save(source)
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));resp=page.goto(base+'/resize-image-dimensions',wait_until='domcontentloaded');page.locator('#preset').select_option('passport');page.locator('#file-input').set_input_files(str(source));page.wait_for_timeout(150);preset=page.locator('#preset').input_value();assert preset=='passport',preset;page.locator('#run-button').click();page.wait_for_function("document.querySelector('#result')&&!document.querySelector('#result').hidden",timeout=30000)
    with page.expect_download(timeout=30000) as ev:page.locator('#result-download-link').click()
    image=Image.open(ev.value.path());assert image.size==(350,450),image.size;page.screenshot(path=str(OUT/f'id165-passport-resize-round{n}.png'));assert not errs;rounds.append({'round':n,'status':resp.status,'preset_after_upload':preset,'download_name':ev.value.suggested_filename,'dimensions':image.size,'page_errors':errs});c.close()
   result={'rounds':rounds};(OUT/'browser-id165-photo-preset-retained.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
