"""Browser-check current how-to claims against initial form controls on affected routes."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/launch-audit-v24/browser-id173-preupload-control-claims.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper
ROUTES=('/ocr-pdf','/translate-pdf','/html-to-pdf','/jpg-to-pdf','/pdf-to-jpg','/pdf-to-word','/pdf-to-excel','/pdf-to-powerpoint','/watermark-pdf')
def main():
 with TemporaryDirectory(prefix='paperplane-id173-') as temp:
  app,base,_=helper.start_server(Path(temp)/'data')
  ev={'routes':{},'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError:
     if app.poll() is not None: raise RuntimeError('server exited')
     time.sleep(.15)
   else: raise RuntimeError('server startup timeout')
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':900})
    page.set_default_timeout(20000)
    page.on('pageerror',lambda e:ev['page_errors'].append(str(e).splitlines()[0][:200]))
    page.on('console',lambda m:ev['console_errors'].append(m.text[:200]) if m.type=='error' else None)
    for route in ROUTES:
     response=page.goto(base+route,wait_until='domcontentloaded')
     page.wait_for_function("document.querySelectorAll('.seo-content .seo-howto-step').length >= 2")
     ev['routes'][route]={
      'status':response.status if response else None,
      'steps':page.locator('.seo-content .seo-howto-step').evaluate_all("els=>els.map(x=>({heading:x.querySelector('h3')?.textContent.trim(),body:x.querySelector('p')?.textContent.trim()}))"),
      'visible_controls_preupload':page.evaluate("""()=>[...document.querySelectorAll('#options input,#options select,#options textarea,#options button')].filter(e=>{let r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.disabled}).map(e=>({id:e.id,label:e.labels?.[0]?.textContent.trim()||e.getAttribute('aria-label')||e.placeholder||''}))""")}
    browser.close()
  finally:
   app.terminate(); app.wait(timeout=5)
  ev['overall']='passed' if all(x['status']==200 and len(x['steps'])==3 and all(s['heading'] and s['body'] for s in x['steps']) for x in ev['routes'].values()) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8')
  print(json.dumps(ev,indent=2))
  if ev['overall']!='passed': raise SystemExit(1)
if __name__=='__main__': main()
