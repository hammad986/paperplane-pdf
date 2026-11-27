from __future__ import annotations
import json,os,socket,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz,uvicorn
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-id157-chat-state-') as td:
 os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'id157-local-admin-key','PAPERPLANE_ADMIN_CODE':'id157-local-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
 sys.path.insert(0,str(root))
 from server import app
 import persistence
 persistence.init_db()
 with fitz.open() as doc:
  for n in range(3):
   p=doc.new_page();p.insert_text((60,70),f'Chat state fixture page {n+1}: distinct marker')
  fixture=Path(td)/'chat-state.pdf';fixture.write_bytes(doc.tobytes())
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=uv.run,daemon=True);thread.start()
 out={'states':[],'page_errors':[],'console_errors':[]}
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   context=browser.new_context(viewport={'width':390,'height':844})
   page=context.new_page()
   page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
   page.on('console',lambda m:out['console_errors'].append(m.text) if m.type=='error' else None)
   def state(label):
    return page.evaluate("""label=>({label,title:document.title,active_document_visible:!document.querySelector('#ai-active-doc-bar').hidden,active_filename:document.querySelector('#ai-doc-name').textContent,empty_state_visible:!document.querySelector('#ai-empty-state').hidden,empty_state_text:document.querySelector('#ai-empty-state').innerText,greeting_count:[...document.querySelectorAll('.chat-bubble.ai')].filter(x=>x.innerText.includes('Your PDF is ready')).length,greeting_cards:[...document.querySelectorAll('.chat-bubble.ai')].map(x=>x.innerText),document_greeting_nodes:document.querySelectorAll('.chat-bubble.ai').length})""",label)
   page.goto(f'http://127.0.0.1:{port}/ai-intelligence',wait_until='domcontentloaded');page.wait_for_function("typeof state !== 'undefined' || document.querySelector('#ai-file-input')")
   page.locator('#ai-file-input').set_input_files(str(fixture));page.wait_for_function("!document.querySelector('#ai-active-doc-bar').hidden",timeout=15000);page.wait_for_timeout(1500)
   first=state('after-upload-settled');page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id157-chat-state-upload-v220.png'),full_page=True);out['states'].append(first)
   page.reload(wait_until='domcontentloaded');page.wait_for_function("typeof window.updateAiDocBar==='function' || document.querySelector('#ai-active-doc-bar')",timeout=10000);page.wait_for_timeout(2200)
   second=state('after-reload-settled');page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id157-chat-state-reload-v220.png'),full_page=True);out['states'].append(second)
   browser.close()
  out['passed']=len(out['states'])==2 and all(x['active_document_visible'] and x['active_filename']=='chat-state.pdf' and not x['empty_state_visible'] and x['greeting_count']==1 and x['document_greeting_nodes']==1 for x in out['states']) and not out['page_errors'] and not out['console_errors']
 finally:uv.should_exit=True;thread.join(timeout=5)
 (root/'reports/launch-audit-v24/browser-id157-chat-state-v220.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
