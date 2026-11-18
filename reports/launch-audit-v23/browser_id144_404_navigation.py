from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id144-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':390,'height':844});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));response=page.goto(base+'/missing-route-for-404',wait_until='domcontentloaded');mobile=page.evaluate("""()=>({navVisible:!!document.querySelector('.site-nav')&&getComputedStyle(document.querySelector('.site-nav')).display!=='none',links:[...document.querySelectorAll('.site-nav-links a')].map(a=>({label:a.innerText.trim(),href:a.getAttribute('href'),rect:(()=>{const r=a.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()})),scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth,mainVisible:!!document.querySelector('main .box')})""")
    assert response.status==404 and mobile['navVisible'] and mobile['mainVisible'] and mobile['scrollWidth']==390 and all(x['rect']['x']>=0 and x['rect']['x']+x['rect']['w']<=390 for x in mobile['links'])
    awaitable=page.screenshot(path=str(OUT/f'id144-404-mobile-round{n}.png'));page.set_viewport_size({'width':1366,'height':900});desktop=page.evaluate("""()=>({navVisible:!!document.querySelector('.site-nav')&&getComputedStyle(document.querySelector('.site-nav')).display!=='none',scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth,mainVisible:!!document.querySelector('main .box')})""")
    assert desktop['navVisible'] and desktop['mainVisible'] and desktop['scrollWidth']==1366
    rounds.append({'round':n,'status':response.status,'mobile':mobile,'desktop':desktop,'page_errors':errors});assert not errors;c.close()
   result={'rounds':rounds};(OUT/'browser-id144-404-navigation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
