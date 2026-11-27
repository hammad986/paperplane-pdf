from __future__ import annotations
import json, os, socket, sys, tempfile, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import uvicorn
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-id140-profile-') as td:
 os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'id140-local-admin-key','PAPERPLANE_ADMIN_CODE':'id140-local-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
 sys.path.insert(0,str(root))
 from server import app
 import persistence
 persistence.init_db()
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=uv.run,daemon=True);thread.start()
 out={'routes':[],'page_errors':[],'console_errors':[]}
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   page=browser.new_page(viewport={'width':1365,'height':900})
   page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
   page.on('console',lambda m:out['console_errors'].append(m.text) if m.type=='error' else None)
   for path in ('/','/apps','/download','/privacy','/terms','/faq'):
    response=page.goto(f'http://127.0.0.1:{port}{path}',wait_until='domcontentloaded')
    card=page.locator('#sidebar-profile-card')
    initial={'domcontentloaded_visible':card.count()>0 and card.is_visible(),'has_badge':card.count()>0 and bool(card.locator('#user-role-badge').inner_text().strip())}
    page.wait_for_timeout(1200)
    out['routes'].append({'path':path,'status':response.status if response else None,'final_path':page.url.split(str(port))[-1],**initial,'settled_visible':card.count()>0 and card.is_visible()})
    page.evaluate("window.scrollTo(0,0)")
   page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id140-profile-card-v220.png'),full_page=True)
   browser.close()
  out['passed']=all(x['status']==200 and x['domcontentloaded_visible'] and x['settled_visible'] and x['has_badge'] for x in out['routes']) and not out['page_errors'] and not out['console_errors']
 finally:uv.should_exit=True;thread.join(timeout=5)
 (root/'reports/launch-audit-v24/browser-id140-profile-card-v220.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
