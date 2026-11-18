from pathlib import Path
from tempfile import TemporaryDirectory
import ast,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
slugs=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'server.py').read_text(encoding='utf-8')).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OPERATION_SLUGS' for t in n.targets))
with TemporaryDirectory(prefix='paperplane-id182-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);results=[];errors=[];page=b.new_page(viewport={'width':1366,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
   for width in (390,1366):
    page.set_viewport_size({'width':width,'height':900})
    for operation,slug in slugs.items():
     resp=page.goto(base+'/'+slug,wait_until='domcontentloaded',timeout=15000);page.wait_for_selector('#run-button',state='attached');page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=8000);page.wait_for_function("(()=>{const e=document.querySelector('#run-button'),s=e&&getComputedStyle(e);return !!s&&s.color!=='rgb(255, 255, 255)'&&s.backgroundColor!=='rgba(0, 0, 0, 0)'})()",timeout=8000);m=page.locator('#run-button').evaluate("""e=>{const s=getComputedStyle(e);return {disabled:e.disabled,color:s.color,background:s.backgroundColor,opacity:s.opacity,text:e.innerText.trim(),rect:(()=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()}}""")
     def rgb(x):
      vals=[float(y) for y in x[x.find('(')+1:x.find(')')].split(',')[:3]];return [v/255 for v in vals]
     def lum(x):
      a=rgb(x);v=[z/12.92 if z<=.04045 else ((z+.055)/1.055)**2.4 for z in a];return .2126*v[0]+.7152*v[1]+.0722*v[2]
     if m['rect']['width']==0 or m['rect']['height']==0:
      results.append({'operation':operation,'slug':slug,'width':width,'status':resp.status,'visible':False,'note':'tool uses a separate AI workspace form'});continue
     if 'rgb' in m['color'] and 'rgb' in m['background']:
      a,z=lum(m['color']),lum(m['background']);m['contrast']=round((max(a,z)+.05)/(min(a,z)+.05),3)
     row={'operation':operation,'slug':slug,'width':width,'status':resp.status,**m};results.append(row)
   fails=[x for x in results if x['status']!=200 or (x.get('visible',True) and (x['disabled'] is False or x.get('contrast',0)<4.5 or x['rect']['width']<=0))]
   summary={'route_count':len(slugs),'views':len(results),'visible_button_views':sum(1 for x in results if x.get('visible',True)),'separate_workspace_views':sum(1 for x in results if not x.get('visible',True)),'failure_count':len(fails),'failures':fails,'sample':results[:3],'page_errors':errors};(OUT/'browser-id182-disabled-cta-contrast.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));assert not fails and not errors;b.close()
 finally:app.terminate();app.wait(timeout=5)
