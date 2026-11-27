"""Stress-test a 69-page image-rich PDF in Chrome and monitor main-thread stalls."""
from __future__ import annotations
import base64,json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reports/launch-audit-v24/browser-id122-heavy-document-responsiveness.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id122-') as td:
  td=Path(td); image=td/'photo.jpg'; source=td/'heavy-69.pdf'
  # One moderately large raster repeated on each page creates real PDF.js decode/render work while keeping fixture size bounded.
  import random
  random.seed(122); pixels=bytes(random.randrange(256) for _ in range(512*512*3))
  Image.frombytes('RGB',(512,512),pixels).save(image,format='JPEG',quality=82)
  with fitz.open() as doc:
   xref=0
   for n in range(1,70):
    pg=doc.new_page(width=612,height=792); pg.insert_text((72,72),f'ID122 PAGE {n}')
    if not xref: xref=doc._get_xref_for_pdf_path if False else 0
    pg.insert_image(fitz.Rect(60,100,552,592),filename=str(image))
   doc.save(source,garbage=4,deflate=True)
  app,base,_=helper.start_server(td/'data'); ev={'fixture_bytes':source.stat().st_size,'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError:
     if app.poll() is not None: raise RuntimeError('server exited')
     time.sleep(.15)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True); page=browser.new_page(viewport={'width':1366,'height':900}); page.set_default_timeout(30000)
    page.add_init_script("""window.__longTasks=[];new PerformanceObserver(list=>list.getEntries().forEach(e=>window.__longTasks.push({duration:e.duration,startTime:e.startTime}))).observe({type:'longtask',buffered:true});""")
    page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200])); page.on('console',lambda m:ev['console_errors'].append(m.text[:200]) if m.type=='error' else None)
    page.goto(base+'/rotate-pdf',wait_until='domcontentloaded'); b64=base64.b64encode(source.read_bytes()).decode('ascii')
    t0=time.perf_counter()
    page.evaluate("""b=>{let a=Uint8Array.from(atob(b),c=>c.charCodeAt(0));let blob=new Blob([a],{type:'application/pdf'});showDownloadResult({output_name:'id122-heavy.pdf',output_size:blob.size,page_count:69},URL.createObjectURL(blob),{blob})}""",b64)
    page.locator('#result-view-studio-btn').click(); page.wait_for_function('state.studio.pdfDoc && state.studio.totalCount===69',timeout=60000); page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=60000)
    ev['studio_load_ms']=round((time.perf_counter()-t0)*1000)
    page.evaluate("""()=>{const a=document.querySelector('#studio-canvas-area');a.scrollTop=a.scrollHeight;a.dispatchEvent(new Event('scroll',{bubbles:true}))}""")
    page.wait_for_function("document.querySelector('#studio-page-stack .studio-page-sheet[data-page=\"69\"] canvas.pdf-page-canvas')?.dataset.rendered==='true'",timeout=60000)
    ev['page69_rendered']=page.locator('#studio-page-stack .studio-page-sheet[data-page="69"] canvas.pdf-page-canvas').get_attribute('data-rendered')
    ev['workspace_switch_ms']=page.evaluate("""async()=>{let t=performance.now();switchWorkspaceView('tool-desk',null,false);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));let desk=performance.now()-t;t=performance.now();switchWorkspaceView('studio',null,false);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return {to_tool_desk_ms:Math.round(desk),back_to_studio_ms:Math.round(performance.now()-t)}}""")
    page.wait_for_timeout(1500)
    ev['long_tasks']=page.evaluate('window.__longTasks'); ev['max_long_task_ms']=round(max((x['duration'] for x in ev['long_tasks']),default=0),1); ev['total_pages']=page.locator('#studio-page-stack .studio-page-sheet').count(); ev['page_count']=page.locator('#studio-page-count').inner_text()
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
  ev['overall']='passed' if ev.get('page69_rendered')=='true' and ev.get('total_pages')==69 and not ev['page_errors'] and not ev['console_errors'] and max(ev['workspace_switch_ms'].values())<1500 else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8'); print(json.dumps(ev,indent=2))
  if ev['overall']!='passed': raise SystemExit(1)
if __name__=='__main__': main()
