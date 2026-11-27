from __future__ import annotations
import json,os,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; VERSION=os.environ.get('PAPERPLANE_PERF_VERSION','v234'); OUT=ROOT/'reports/launch-audit-v24'/f'browser-id122-{VERSION}-notes-performance.json'
SOURCE=Path(r'C:\Users\mdham\Downloads\notes.pdf')
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 expected=[]
 with fitz.open(SOURCE) as source: expected=[p.get_text() for p in source]
 with TemporaryDirectory(prefix=f'paperplane-{VERSION}-id122-performance-') as tmp:
  root=Path(tmp); app,base,_=helper.start_server(root/'data')
  result={'source_bytes':SOURCE.stat().st_size,'source_pages':len(expected),'cpu_throttle':4,'rounds':[],'page_errors':[],'unexpected_console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.15)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for round_no in (1,2):
     page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=3)
     cdp=page.context.new_cdp_session(page); cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
     page.add_init_script("window.__id122LongTasks=[];new PerformanceObserver(list=>list.getEntries().forEach(e=>window.__id122LongTasks.push(e.duration))).observe({type:'longtask',buffered:true});window.__id122Started=performance.now()")
     page.on('pageerror',lambda e:result['page_errors'].append(str(e).splitlines()[0][:220]))
     page.on('console',lambda m:result['unexpected_console_errors'].append(m.text[:220]) if m.type=='error' else None)
     nav=page.goto(base+'/studio',wait_until='domcontentloaded'); assert nav and nav.status==200
     page.locator('#studio-file-input').set_input_files(str(SOURCE))
     page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69' && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=120000)
     first_ready=page.evaluate('performance.now()-window.__id122Started')
     pixel=len(page.locator('#pdf-canvas').screenshot())
     page.locator('#page-jump-input').fill('40'); page.locator('#page-jump-input').press('Enter')
     page.wait_for_function("state.studio.currentPage===40 && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=90000)
     page.wait_for_timeout(500)
     jump_canvas=page.locator('#pdf-canvas').screenshot(path=str(OUT.parent/f'browser-id122-{VERSION}-notes-page40-round{round_no}.png'))
     with page.expect_download(timeout=60000) as dl: page.locator('#save-studio-btn').click()
     exported=root/f'notes-round{round_no}.pdf'; dl.value.save_as(exported)
     with fitz.open(exported) as out: out_text=[p.get_text() for p in out]
     long_tasks=page.evaluate('window.__id122LongTasks')
     item={'round':round_no,'first_page_ready_ms':round(first_ready,1),'page1_screenshot_bytes':pixel,'page40_rendered':True,'page_count':len(out_text),'exact_page_text_order':out_text==expected,'long_tasks_over_50ms':sum(x>50 for x in long_tasks),'long_tasks_over_250ms':sum(x>250 for x in long_tasks),'max_long_task_ms':round(max(long_tasks,default=0),1),'document_width':page.evaluate('document.documentElement.scrollWidth'),'viewport_width':390,'page40_screenshot':f'browser-id122-{VERSION}-notes-page40-round{round_no}.png'}
     assert item['page_count']==69 and item['exact_page_text_order'] and item['document_width']<=392,item
     result['rounds'].append(item); page.close()
    browser.close()
   result['result']='passed' if len(result['rounds'])==2 and not result['page_errors'] and not result['unexpected_console_errors'] else 'failed'
   OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
   if result['result']!='passed': raise SystemExit(1)
  finally: app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
