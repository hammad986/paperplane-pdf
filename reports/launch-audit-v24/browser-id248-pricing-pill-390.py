import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id248-pricing-pill-390.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id248-') as tmp:
 app,base,_=h.start_server(Path(tmp)/'data')
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':390,'height':844});e={'page_errors':[],'console_errors':[]};page.on('pageerror',lambda x:e['page_errors'].append(str(x)));page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None);r=page.goto(base+'/pricing',wait_until='domcontentloaded');page.wait_for_timeout(250);e['route_status']=r.status if r else None;e['viewport']=page.evaluate("""()=>{const x=document.querySelector('#mobile-view-pill'),p=x?.parentElement;const r=e=>{if(!e)return null;const b=e.getBoundingClientRect(),s=getComputedStyle(e);return{x:b.x,y:b.y,right:b.right,width:b.width,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,whiteSpace:s.whiteSpace,textOverflow:s.textOverflow,display:s.display,text:e.innerText}};return{pill:r(x),parent:r(p),documentWidth:document.documentElement.scrollWidth,viewport:innerWidth}}""");page.screenshot(path=str(OUT.parent/'browser-id248-pricing-pill-390.png'));e['passed']=e['route_status']==200 and e['viewport']['pill']['text']=='Pricing' and e['viewport']['documentWidth']<=390 and not e['page_errors'] and not e['console_errors'];OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
