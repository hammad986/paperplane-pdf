"""Check result-card viewport placement and Studio export filename visibility."""
from __future__ import annotations
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reports/launch-audit-v24/browser-id213-result-visibility-export-name.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id213-') as td:
  td=Path(td); src=td/'source.pdf'
  with fitz.open() as d:
   p=d.new_page(); p.insert_text((72,90),'ID213 result placement source'); d.save(src)
  app,base,_=helper.start_server(td/'data'); ev={'rounds':[],'page_errors':[],'console_errors':[]}
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
    for w,h in ((390,844),(1366,900)):
     page=browser.new_page(viewport={'width':w,'height':h},accept_downloads=True)
     page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]))
     page.on('console',lambda m:ev['console_errors'].append(m.text[:200]) if m.type=='error' else None)
     page.goto(base+'/rotate-pdf',wait_until='domcontentloaded'); page.locator('#file-input').set_input_files(str(src)); page.wait_for_function('state.files?.length===1'); page.locator('#run-button').click(); page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000)
     page.wait_for_timeout(500)
     result=page.evaluate("""()=>{let r=document.querySelector('#result').getBoundingClientRect(),b=document.querySelector('#result-download-link').getBoundingClientRect();return {scrollY,viewport:innerHeight,result:{top:r.top,bottom:r.bottom},download:{top:b.top,bottom:b.bottom,visible:b.bottom>0&&b.top<innerHeight},title:document.querySelector('#result-title')?.textContent}}""")
     with page.expect_download(timeout=30000) as dl: page.locator('#result-download-link').click()
     saved=td/f'rotate-{w}.pdf'; dl.value.save_as(saved)
     with fitz.open(saved) as out: content=out.page_count==1 and 'ID213 result placement source' in out[0].get_text()
     # Studio file export path and user-facing name.
     page.locator('#result-view-studio-btn').click(); page.wait_for_function('state.studio.pdfDoc && state.studio.totalCount===1')
     with page.expect_download(timeout=30000) as export: page.locator('#save-studio-btn').click()
     filename=export.value.suggested_filename
     page.wait_for_timeout(100)
     toast=page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else ''
     ev['rounds'].append({'viewport':[w,h],'result':result,'download_content_checked':content,'studio_suggested_filename':filename,'studio_toast':toast,'filename_in_toast':filename in toast})
     page.close()
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
  ev['overall']='passed' if len(ev['rounds'])==2 and all(x['result']['download']['visible'] and x['download_content_checked'] and x['studio_suggested_filename'] and x['filename_in_toast'] for x in ev['rounds']) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8'); print(json.dumps(ev,indent=2))
  if ev['overall']!='passed': raise SystemExit(1)
if __name__=='__main__': main()


