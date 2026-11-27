from __future__ import annotations
import json, os, socket, sys, tempfile, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import uvicorn
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-id176-nav-') as td:
 os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'id176-local-admin-key','PAPERPLANE_ADMIN_CODE':'id176-local-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
 sys.path.insert(0,str(root))
 from server import app
 import persistence
 persistence.init_db()
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=uv.run,daemon=True);thread.start()
 out={'rounds':[],'page_errors':[],'console_errors':[]}
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
   page.goto(f'http://127.0.0.1:{port}/',wait_until='domcontentloaded');page.wait_for_function("()=>!document.body.classList.contains('auth-pending')")
   for index,operation in enumerate(('rotate','merge'),1):
    page.evaluate("showToast('Previous view notification', 'warning', 15000)")
    page.locator('#tab-ai-view').click();page.wait_for_function("()=>document.title.startsWith('AI Document Intelligence')")
    toast_after_nav=page.locator('.toast-notice').count()
    page.locator('#tab-tool-desk-view').click();page.wait_for_function("()=>document.title.startsWith('PDF Tools')")
    page.evaluate('(op)=>selectOperation(op)',operation)
    immediate=page.locator('#desk-breadcrumb-label').inner_text()
    page.wait_for_timeout(1100)
    settled=page.locator('#desk-breadcrumb-label').inner_text()
    out['rounds'].append({'round':index,'operation':operation,'toast_after_navigation':toast_after_nav,'immediate_breadcrumb':immediate,'settled_breadcrumb':settled,'toast_after_settle':page.locator('.toast-notice').count()})
   page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id176-toast-breadcrumb-v220.png'),full_page=True)
   browser.close()
  out['passed']=len(out['rounds'])==2 and all(x['toast_after_navigation']==0 and x['immediate_breadcrumb']==x['settled_breadcrumb'] and x['toast_after_settle']==0 for x in out['rounds']) and not out['page_errors'] and not out['console_errors']
 finally:uv.should_exit=True;thread.join(timeout=5)
 (root/'reports/launch-audit-v24/browser-id176-toast-breadcrumb-v220.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
