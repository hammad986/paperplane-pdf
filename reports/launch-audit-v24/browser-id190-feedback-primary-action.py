import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id190-feedback-primary-action.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id190-') as tmp:
 base_dir=Path(tmp);app,base,identities=h.start_server(base_dir/'db');pdfs=[]
 for i in (1,2):
  pth=base_dir/f'merge-{i}.pdf'
  with fitz.open() as d:d.new_page().insert_text((72,72),f'Merge {i}');d.save(pth)
  pdfs.append(pth)
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.add_cookies([{'name':'paperplane_token','value':identities['accounts'][0][1],'url':base,'httpOnly':True,'secure':False,'sameSite':'Lax'}]);page=ctx.new_page();errors=[];console_errors=[];page.on('pageerror',lambda x:errors.append(str(x)));page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None);page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_function('Boolean(window.state?.user?.user_id)',timeout=10000);page.locator('#file-input').set_input_files([str(x) for x in pdfs]);page.wait_for_timeout(1000);page.wait_for_function("document.querySelector('#pp-feedback-launcher')?.hidden === false",timeout=10000);page.locator('#run-button').scroll_into_view_if_needed();page.evaluate('window.scrollBy(0,-275)');page.wait_for_timeout(300)
   e=page.evaluate("""()=>{const r=e=>{const b=e.getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,bottom:b.bottom,width:b.width,height:b.height,visible:!!(b.width&&b.height)&&getComputedStyle(e).visibility!=='hidden'&&!e.hidden}};const launcher=document.querySelector('#pp-feedback-launcher');const action=document.querySelector('#run-button');const nav=document.querySelector('.mobile-workspace-bar');const a=r(action),f=r(launcher),n=r(nav);return {action:a,feedback:f,nav:n,actionFeedbackOverlap:a.visible&&f.visible&&a.x<f.right&&a.right>f.x&&a.y<f.bottom&&a.bottom>f.y,viewport:{w:innerWidth,h:innerHeight},documentWidth:document.documentElement.scrollWidth}}""");e['route_status']=page.url;e['page_errors']=errors;e['console_errors']=console_errors;e['passed']=not e['actionFeedbackOverlap'] and not errors and not console_errors;page.screenshot(path=str(OUT.parent/'browser-id190-feedback-primary-action.png'),full_page=False);OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));browser.close();
   if not e['passed']: raise SystemExit(1)
 finally:app.terminate();app.wait(timeout=5)
