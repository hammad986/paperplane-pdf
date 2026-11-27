from __future__ import annotations
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from io import BytesIO
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/launch-audit-v24/browser-id30-v234-notes-canvas-visibility.json'
SOURCE=Path(r'C:\Users\mdham\Downloads\notes.pdf')
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def pixel_check(png):
 image=Image.open(BytesIO(png)).convert('RGB')
 pixels=list(image.getdata())
 ink=sum(1 for r,g,b in pixels if min(r,g,b)<180)
 return {'screenshot_width':image.width,'screenshot_height':image.height,'nonwhite_pixels':ink}

def main():
 if not SOURCE.is_file(): raise FileNotFoundError(SOURCE)
 with TemporaryDirectory(prefix='paperplane-v234-id30-notes-') as tmp:
  app,base,_=helper.start_server(Path(tmp)/'data')
  result={'source':str(SOURCE),'source_bytes':SOURCE.stat().st_size,'rounds':[],'page_errors':[],'unexpected_console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.15)
   else: raise RuntimeError('local app did not start')
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for round_no in (1,2):
     page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
     page.on('pageerror',lambda e:result['page_errors'].append(str(e).splitlines()[0][:240]))
     page.on('console',lambda m:result['unexpected_console_errors'].append(m.text[:240]) if m.type=='error' else None)
     response=page.goto(base+'/studio',wait_until='domcontentloaded'); assert response and response.status==200
     page.locator('#studio-file-input').set_input_files(str(SOURCE))
     page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=90000)
     checks=[]
     for width,height in ((390,844),(820,900),(1366,900)):
      page.set_viewport_size({'width':width,'height':height}); page.wait_for_timeout(1800)
      png=page.locator('#pdf-canvas').screenshot(timeout=15000); pix=pixel_check(png)
      metrics=page.evaluate('''()=>{const c=document.querySelector('#pdf-canvas'),e=document.querySelector('#save-studio-btn'),n=document.querySelector('.mobile-workspace-bar');const cr=c.getBoundingClientRect(),er=e.getBoundingClientRect(),nr=n?.getBoundingClientRect();return{width:innerWidth,documentWidth:document.documentElement.scrollWidth,pageCount:document.querySelector('#page-total-indicator')?.textContent,rendered:c?.dataset.rendered,canvasCSS:{width:cr.width,height:cr.height},export:{left:er.left,right:er.right,top:er.top,bottom:er.bottom},nav:nr?{top:nr.top,bottom:nr.bottom,height:nr.height}:null,exportInViewport:er.left>=0&&er.right<=innerWidth,exportAboveDock:!nr||nr.height===0||er.bottom<=nr.top+1}}''')
      metrics.update(pix); metrics['screenshot']=f'browser-id30-v234-notes-round{round_no}-{width}.png'
      page.screenshot(path=str(OUT.parent/metrics['screenshot']))
      assert metrics['pageCount']=='69' and metrics['rendered']=='true' and metrics['nonwhite_pixels']>300,metrics
      assert metrics['documentWidth']<=width+2 and metrics['exportInViewport'] and metrics['exportAboveDock'],metrics
      checks.append(metrics)
     result['rounds'].append({'round':round_no,'checks':checks})
     page.close()
    browser.close()
   result['result']='passed' if len(result['rounds'])==2 and not result['page_errors'] and not result['unexpected_console_errors'] else 'failed'
   OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
   if result['result']!='passed': raise SystemExit(1)
  finally: app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
