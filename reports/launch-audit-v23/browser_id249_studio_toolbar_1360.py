from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id249-') as tmp:
 app,base,_=helper.start_server(Path(tmp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  rows=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1360,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/studio',wait_until='networkidle');page.evaluate('document.fonts.ready');page.wait_for_timeout(1200)
    m=page.evaluate("""()=>{const t=document.querySelector('.studio-toolbar'),p=t.querySelector('.studio-primary-ribbon'),r=t.getBoundingClientRect();const g=[...p.querySelectorAll(':scope > .studio-tool-group')].map(e=>({className:e.className,top:Math.round(e.getBoundingClientRect().top),left:Math.round(e.getBoundingClientRect().left),right:Math.round(e.getBoundingClientRect().right),width:Math.round(e.getBoundingClientRect().width)}));return{toolbar:{x:r.x,y:r.y,width:r.width,height:r.height},primary:{height:Math.round(p.getBoundingClientRect().height),scrollWidth:p.scrollWidth,clientWidth:p.clientWidth,groups:g,exportVisible:!!p.querySelector('.studio-export-group'),labels:[...p.querySelectorAll('.tool-btn-text')].slice(0,5).map(e=>getComputedStyle(e).display)},documentWidth:document.documentElement.scrollWidth,viewport:innerWidth}}""")
    rows.append({'round':n,**m,'page_errors':errors})
    page.screenshot(path=str(OUT/f'id249-studio-1360-round{n}.png'));page.close()
    tops=[g['top'] for g in m['primary']['groups'] if g['width']>0]
    export=next(g for g in m['primary']['groups'] if 'studio-export-group' in g['className'])
    ribbon_right=m['toolbar']['x']+m['toolbar']['width']
    assert max(tops)-min(tops)<=8 and m['primary']['height']<=50 and export['right']<=ribbon_right,(n,m)
    assert m['documentWidth']==m['viewport'] and not errors,(n,m,errors)
    tops=sorted(set(g['top'] for g in m['primary']['groups'] if g['width']>0))
    print(json.dumps({'round':n,**m,'page_errors':errors}))
   browser.close()
  (OUT/'browser-id249-studio-toolbar-1360.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');print(json.dumps(rows,indent=2))
 finally:app.terminate();app.wait(timeout=5)
