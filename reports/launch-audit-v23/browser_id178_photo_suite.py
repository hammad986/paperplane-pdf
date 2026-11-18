from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id178-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':390,'height':844});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));resp=page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.locator('#mobile-menu-btn').click();page.locator('.nav-category-tab[data-category="Photo"]').click();page.wait_for_function("document.querySelector('#view-tool-desk-directory')?.hidden===false && document.querySelector('#view-ai')?.hidden!==false",timeout=5000)
    data=page.evaluate("""()=>({directoryVisible:!document.querySelector('#view-tool-desk-directory').hidden,aiVisible:!document.querySelector('#view-ai-studio').hidden,category:document.querySelector('.nav-category-tab[data-category="Photo"]')?.classList.contains('active'),filter:document.querySelector('#tool-desk-directory-filters [data-desk-category="photo"]')?.classList.contains('active'),cards:[...document.querySelectorAll('#tool-desk-tools-catalog a')].map(a=>a.href)})""");assert resp.status==200 and data['directoryVisible'] and not data['aiVisible'] and data['filter'] and len(data['cards'])==4,data;assert not errors;page.screenshot(path=str(OUT/f'id178-photo-suite-round{n}.png'));rounds.append({'round':n,'status':resp.status,**data,'page_errors':errors});c.close()
   result={'rounds':rounds};(OUT/'browser-id178-photo-suite-selection.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
