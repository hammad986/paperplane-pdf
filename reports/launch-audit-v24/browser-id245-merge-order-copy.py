"""Verify Merge copy, file order controls, and output order are aligned."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reports/launch-audit-v24/browser-id245-merge-order-copy.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id245-') as td:
  td=Path(td); files=[]
  for i in (1,2):
   p=td/f'id245-{i}.pdf'
   with fitz.open() as d:
    pg=d.new_page(); pg.insert_text((72,90),f'ID245 SOURCE {i}'); d.save(p)
   files.append(p)
  app,base,_=helper.start_server(td/'data'); ev={'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError:
     if app.poll() is not None: raise RuntimeError('server exited')
     time.sleep(.15)
   else: raise RuntimeError('startup timeout')
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True)
    page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]))
    page.on('console',lambda m:ev['console_errors'].append(m.text[:200]) if m.type=='error' else None)
    res=page.goto(base+'/merge-pdf',wait_until='domcontentloaded'); page.locator('#file-input').set_input_files([str(x) for x in files]); page.wait_for_function('state.files?.length===2')
    ev['http_status']=res.status if res else None
    ev['description']=page.locator('#tool-description').inner_text()
    ev['how_to']=page.locator('.seo-content .seo-howto-step').evaluate_all("es=>es.map(e=>e.querySelector('h3')?.innerText+' — '+e.querySelector('p')?.innerText)")
    ev['file_list']=page.locator('#file-list').inner_text()
    ev['reorder_controls']=page.locator('#file-list button[aria-label*=move i],#file-list [draggable=true],#file-list .drag-handle').count()
    ev['selected_names']=page.evaluate('state.files.map(f=>f.name)')
    page.locator('#run-button').click(); page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000)
    with page.expect_download(timeout=30000) as dl: page.locator('#result-download-link').click()
    output=td/dl.value.suggested_filename; dl.value.save_as(output)
    with fitz.open(output) as d: ev['output']={'pages':d.page_count,'text':[d[i].get_text().strip() for i in range(d.page_count)]}
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
  ev['overall']='passed' if ev.get('http_status')==200 and 'order you add' in ev.get('description','').lower() and ev.get('selected_names')==['id245-1.pdf','id245-2.pdf'] and ev.get('reorder_controls')==0 and ev.get('output',{}).get('pages')==2 and 'ID245 SOURCE 1' in ev['output']['text'][0] and 'ID245 SOURCE 2' in ev['output']['text'][1] and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8'); print(json.dumps(ev,indent=2))
  if ev['overall']!='passed': raise SystemExit(1)
if __name__=='__main__': main()
