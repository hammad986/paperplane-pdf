from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id157-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));resp=page.goto(base+'/ai-intelligence',wait_until='domcontentloaded');page.wait_for_selector('#chat-messages');counts=[]
    for pause in (150,1000,2500):
     page.wait_for_timeout(pause);counts.append(page.evaluate("""()=>({emptyState:document.querySelectorAll('#chat-messages #ai-empty-state').length,heading:[...document.querySelectorAll('#chat-messages strong')].filter(e=>e.textContent.trim()==='What can I help with?').length,greetingMessages:document.querySelectorAll('#chat-messages .ai-message').length,visibleWelcome:[...document.querySelectorAll('#chat-messages .ai-empty-state')].filter(e=>e.getBoundingClientRect().height>0).length})"""))
    page.screenshot(path=str(OUT/f'id157-ai-welcome-round{n}.png'));item={'round':n,'status':resp.status,'counts_by_settle_time':counts,'page_errors':errs};assert resp.status==200 and all(x['emptyState']==1 and x['heading']==1 and x['greetingMessages']==0 and x['visibleWelcome']==1 for x in counts) and not errs
    rounds.append(item);c.close()
   res={'rounds':rounds};(OUT/'browser-id157-ai-welcome-count.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
