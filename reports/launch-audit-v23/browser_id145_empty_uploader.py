from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id145-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));routes=[]
    for path in ('/merge-pdf','/compress-pdf','/rotate-pdf'):
     resp=page.goto(base+path,wait_until='domcontentloaded');page.wait_for_selector('#dropzone',state='visible');page.wait_for_timeout(250)
     dims=page.evaluate("""()=>{const d=document.querySelector('#dropzone'),l=document.querySelector('#file-list'),a=d.getBoundingClientRect(),b=l.getBoundingClientRect(),s=getComputedStyle(l);return {drop:{x:a.x,y:a.y,w:a.width,h:a.height},list:{x:b.x,y:b.y,w:b.width,h:b.height,display:s.display,minHeight:s.minHeight,padding:s.padding,children:l.children.length,text:l.innerText.trim()},gap:b.top-a.bottom}}""")
     routes.append({'path':path,'status':resp.status,'geometry':dims});
    page.screenshot(path=str(OUT/f'id145-empty-uploader-round{n}.png'));rounds.append({'round':n,'routes':routes,'page_errors':errs});assert not errs;c.close()
   result={'rounds':rounds};(OUT/'browser-id145-empty-uploader-space.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
