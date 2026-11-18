from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id173-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':390,'height':844});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));resp=page.goto(base+'/translate-pdf',wait_until='domcontentloaded');page.wait_for_selector('#target_language');info=page.evaluate("""()=>{const e=document.querySelector('#target_language'),r=e.getBoundingClientRect();return {visible:r.width>0&&r.height>0,disabled:e.disabled,value:e.value,options:[...e.options].map(o=>o.value),selectedFiles:document.querySelector('#file-input')?.files?.length||0,stepHeading:document.querySelector('.seo-content .seo-howto-step:nth-child(2) h3')?.textContent.trim(),stepBody:document.querySelector('.seo-content .seo-howto-step:nth-child(2) p')?.textContent.trim()}}""");assert resp.status==200 and info['visible'] and len(info['options'])>1 and info['selectedFiles']==0 and 'visible selector' in info['stepHeading'] and 'available before upload' in info['stepBody'],info;assert not errors;page.screenshot(path=str(OUT/f'id173-translate-control-before-upload-round{n}.png'));rounds.append({'round':n,'status':resp.status,**info,'page_errors':errors});c.close()
   result={'rounds':rounds};(OUT/'browser-id173-translate-control-timing.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
