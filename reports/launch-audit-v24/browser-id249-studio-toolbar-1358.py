import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id249-studio-toolbar-1358.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id249-') as tmp:
 td=Path(tmp);pdf=td/'toolbar.pdf'
 with fitz.open() as d:d.new_page().insert_text((72,72),'Studio toolbar layout fixture');d.save(pdf)
 app,base,_=h.start_server(td/'data')
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1358,'height':900});e={'page_errors':[],'console_errors':[]};page.on('pageerror',lambda x:e['page_errors'].append(str(x)));page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None);r=page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf));page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1'",timeout=20000);page.wait_for_timeout(800);e['route_status']=r.status if r else None;e['metrics']=page.evaluate("""()=>{const q=s=>document.querySelector(s),rr=e=>{if(!e)return null;const b=e.getBoundingClientRect();return{x:b.x,y:b.y,right:b.right,bottom:b.bottom,width:b.width,height:b.height}};const exp=q('#save-studio-btn'),rib=q('.studio-primary-ribbon'),tb=q('#studio-toolbar');return{viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,toolbar:rr(tb),ribbon:rr(rib),export:rr(exp),exportText:exp?.innerText,primaryChildren:[...rib.children].map(x=>({text:(x.innerText||'').trim().slice(0,40),rect:rr(x)}))}}""");page.screenshot(path=str(OUT.parent/'browser-id249-studio-toolbar-1358.png'));e['passed']=e['route_status']==200 and e['metrics']['export']['y']>=e['metrics']['ribbon']['y'] and e['metrics']['export']['bottom']<=e['metrics']['ribbon']['bottom'] and e['metrics']['documentWidth']<=1358 and not e['page_errors'] and not e['console_errors'];OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
