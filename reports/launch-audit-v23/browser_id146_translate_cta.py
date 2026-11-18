from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id146-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rows=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':390,'height':844});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));resp=page.goto(base+'/translate-pdf',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#run-button')&&document.body.classList.contains('light-mode')")
    page.wait_for_timeout(800)
    page.evaluate("()=>{state.operations.translate.available=true;state.operations.translate.status='AVAILABLE';updateButton()}")
    page.wait_for_function("document.querySelector('#run-button')?.innerText.includes('Select files to continue')")
    style=page.locator('#run-button').evaluate("""e=>{const s=getComputedStyle(e),rgb=v=>v.match(/[\\d.]+/g).slice(0,3).map(Number),lum=v=>{const c=rgb(v).map(x=>x/255<=.04045?x/255/12.92:((x/255+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]},fg=lum(s.color),bg=lum(s.backgroundColor),ratio=(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05),r=e.getBoundingClientRect();return {text:e.innerText.trim(),disabled:e.disabled,fg:s.color,bg:s.backgroundColor,border:s.borderColor,opacity:s.opacity,contrast_ratio:ratio,rect:{x:r.x,y:r.y,w:r.width,h:r.height}}}""")
    item={'round':n,'status':resp.status,'button':style,'page_errors':errors};print(json.dumps(item,indent=2));rows.append(item);assert resp.status==200 and style['text'].startswith('Select files to continue') and style['disabled'] and style['opacity']=='1' and style['contrast_ratio']>=4.5 and not errors
    page.screenshot(path=str(OUT/f'id146-translate-cta-round{n}.png'));c.close()
   result={'rounds':rows};(OUT/'browser-id146-translate-cta-contrast.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
