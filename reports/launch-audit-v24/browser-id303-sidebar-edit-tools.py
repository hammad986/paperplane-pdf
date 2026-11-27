import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id303-sidebar-edit-tools.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id303-') as td:
 app,base,_=h.start_server(Path(td)/'data')
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1366,'height':900});e={'page_errors':[],'console_errors':[]};page.on('pageerror',lambda x:e['page_errors'].append(str(x)));page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None);r=page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.locator('.nav-category-tab[data-category="Edit"]').click();page.wait_for_function("document.querySelector('.sidebar-tool-item[data-select-operation=compare]')");edit_items=page.locator('.sidebar-tool-item').evaluate_all("xs=>xs.map(x=>({key:x.dataset.selectOperation,label:x.innerText.trim()}))");page.locator('.nav-category-tab[data-category="Security"]').click();page.wait_for_function("document.querySelector('.sidebar-tool-item[data-select-operation=redact]')");security_items=page.locator('.sidebar-tool-item').evaluate_all("xs=>xs.map(x=>({key:x.dataset.selectOperation,label:x.innerText.trim()}))");e.update({'status':r.status if r else None,'edit_items':edit_items,'security_items':security_items,'compare_count':sum(x['key']=='compare' for x in edit_items),'metadata_count':sum(x['key']=='metadata' for x in edit_items),'sign_count':sum(x['key']=='sign' for x in security_items),'redact_count':sum(x['key']=='redact' for x in security_items)});page.screenshot(path=str(OUT.parent/'browser-id303-sidebar-edit-tools.png'));e['passed']=e['status']==200 and all(e[k]==1 for k in ('compare_count','metadata_count','sign_count','redact_count')) and not e['page_errors'] and not e['console_errors'];OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
