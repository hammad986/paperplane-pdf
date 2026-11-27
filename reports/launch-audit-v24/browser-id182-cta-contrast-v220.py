from __future__ import annotations
import io,json,os,socket,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image
from collections import Counter
import uvicorn
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-cta-contrast-') as td:
 os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'cta-local-admin-key','PAPERPLANE_ADMIN_CODE':'cta-local-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
 sys.path.insert(0,str(root))
 from server import app,OPERATION_SLUGS
 import persistence
 persistence.init_db()
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=uv.run,daemon=True);thread.start()
 out={'viewports':[390,1365],'routes':[],'errors':[]}
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for width in out['viewports']:
    page=browser.new_page(viewport={'width':width,'height':844 if width<600 else 900})
    page.on('pageerror',lambda e:out['errors'].append(str(e)))
    for operation,slug in OPERATION_SLUGS.items():
     response=page.goto(f'http://127.0.0.1:{port}/{slug}',wait_until='domcontentloaded');page.wait_for_function("typeof selectOperation==='function'");page.evaluate('(op)=>selectOperation(op)',operation);page.wait_for_function("document.querySelector('#run-button')?.checkVisibility()")
     data=page.evaluate("""()=>{const b=document.querySelector('#run-button');if(!b)return null;const s=getComputedStyle(b),r=b.getBoundingClientRect();return{text:b.innerText,disabled:b.disabled,fg:s.color,bg:s.backgroundColor,bg_image:s.backgroundImage,opacity:s.opacity,width:r.width,x:r.x,right:r.right,body:document.body.className,html:document.documentElement.className,theme:document.documentElement.dataset.theme,inline:b.getAttribute('style'),children:[...b.querySelectorAll('*')].map(x=>({text:x.textContent,color:getComputedStyle(x).color,style:x.getAttribute('style')})),sheets:[...document.styleSheets].map(x=>x.href),ruleMatches:[...document.styleSheets].flatMap(x=>{try{return [...x.cssRules].filter(r=>r.selectorText?.includes('#run-button:disabled')).map(r=>({selector:r.selectorText,css:r.cssText}))}catch(e){return []}})}}""")
     if data:
      shot=Image.open(io.BytesIO(page.locator('#run-button').screenshot())).convert('RGB');w,h=shot.size
      palette=Counter(shot.getdata());bg=palette.most_common(1)[0][0]
      def lum(rgb):
       vals=[v/255 for v in rgb];vals=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in vals];return .2126*vals[0]+.7152*vals[1]+.0722*vals[2]
      bl=lum(bg);choices=[(max(bl,lum(c))+.05)/(min(bl,lum(c))+.05) for c,n in palette.items() if c!=bg and n>=20];contrast=max(choices,default=0)
      if operation=='merge':
       shot.save(root/f'reports/launch-audit-v24/browser-id182-disabled-cta-{width}.png')
      out['routes'].append({'op':operation,'slug':slug,'viewport':width,'http':response.status if response else None,**data,'pixel_bg':bg,'contrast':contrast})
    page.close()
   browser.close()
  out['failed']=[x for x in out['routes'] if x['http']!=200 or not x['disabled'] or x['contrast'] is None or x['contrast']<4.5 or x['x']<0 or x['right']>x['viewport']]
  out['passed']=len(out['routes'])==len(OPERATION_SLUGS)*2 and not out['failed'] and not out['errors']
 finally:uv.should_exit=True;thread.join(timeout=5)
 (root/'reports/launch-audit-v24/browser-id182-cta-contrast-v220.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps({'passed':out['passed'],'route_count':len(out['routes']),'failed':out['failed'][:8],'errors':out['errors']},indent=2))
