from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id159-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));resp=page.goto(base+'/',wait_until='domcontentloaded');samples=[]
    for pause in (0,100,500,1500,3000):
     if pause:page.wait_for_timeout(pause)
     samples.append(page.evaluate("""()=>({loading:[...document.querySelectorAll('body *')].filter(e=>e.children.length===0&&e.textContent.trim().includes('Loading tools')).map(e=>({text:e.textContent.trim(),visible:e.getBoundingClientRect().height>0})),h1:[...document.querySelectorAll('h1')].map(e=>e.textContent.trim()),bodyText:document.body.innerText.slice(0,600),width:document.documentElement.scrollWidth,viewport:innerWidth})"""))
    page.screenshot(path=str(OUT/f'id159-home-first-paint-round{n}.png'));item={'round':n,'status':resp.status,'samples':samples,'page_errors':errs};assert resp.status==200 and all(not any(x['visible'] for x in s['loading']) and s['width']<=s['viewport'] for s in samples) and not errs
    rounds.append(item);c.close()
   res={'rounds':rounds};(OUT/'browser-id159-home-first-paint.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
