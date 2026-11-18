from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id142-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':390,'height':844});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.locator('#tool-desk-search').fill('translate');page.wait_for_function("document.querySelector('#tool-desk-search-meta')?.textContent.includes('found')")
    label=page.locator('#tool-desk-search-meta').inner_text();cards=page.locator('#tool-desk-tools-catalog .home-tool-card');links=cards.evaluate_all("es=>es.map(e=>e.getAttribute('href'))");result={'round':n,'label':label,'card_count':cards.count(),'routes':links,'page_errors':errors};rounds.append(result);assert label.startswith('1 tool found') and len(links)==1 and links[0]=='/translate-pdf' and not errors
    page.screenshot(path=str(OUT/f'id142-search-grammar-round{n}.png'));c.close()
   report={'rounds':rounds};(OUT/'browser-id142-search-singular.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
