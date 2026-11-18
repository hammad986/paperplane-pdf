from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id125-') as temp:
 root=Path(temp);pdf=root/'toolbar.pdf'
 with fitz.open() as d:d.new_page().insert_text((72,72),'Studio toolbar geometry');d.save(pdf)
 app,base,_=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);rows=[]
   for n in (1,2):
    ctx=browser.new_context(viewport={'width':1920,'height':1080});page=ctx.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
    page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf));page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
    data=page.evaluate("""()=>{const t=document.querySelector('#studio-toolbar');const r=t.getBoundingClientRect();const groups=[...t.querySelectorAll('.studio-primary-ribbon > *')].filter(e=>getComputedStyle(e).display!=='none');return {toolbar:{x:r.x,y:r.y,width:r.width,height:r.height},groupRows:[...new Set(groups.map(e=>Math.round(e.getBoundingClientRect().top)))],groups:groups.map(e=>({name:e.getAttribute('title')||e.id||e.className,x:Math.round(e.getBoundingClientRect().x),y:Math.round(e.getBoundingClientRect().y),width:Math.round(e.getBoundingClientRect().width),height:Math.round(e.getBoundingClientRect().height)})),scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth}}""")
    page.screenshot(path=str(OUT/f'id125-studio-toolbar-round{n}.png'));rows.append({'round':n,**data,'page_errors':errs});ctx.close()
   res={'rounds':rows};(OUT/'browser-id125-studio-toolbar-geometry.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
