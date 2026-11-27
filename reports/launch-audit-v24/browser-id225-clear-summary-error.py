from __future__ import annotations
import json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'browser-id225-clear-summary-error.json'
with TemporaryDirectory(prefix='paperplane-v24-id225-') as temp:
 tmp=Path(temp); data=tmp/'data'; data.mkdir(); pdf=tmp/'fail-summary.pdf'
 with fitz.open() as doc:
  page=doc.new_page(); page.insert_text((72,72),'Controlled summary failure fixture.'); doc.save(pdf)
 with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
 env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}
 env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(data),'PAPERPLANE_PORT':str(port),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(48),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(32),'PAPERPLANE_SESSION_SECRET':secrets.token_urlsafe(48),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT)})
 app=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 e={'page_errors':[],'console_errors':[]}
 try:
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
   except OSError: time.sleep(.2)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True); page=browser.new_page(viewport={'width':390,'height':844})
   page.on('pageerror',lambda x:e['page_errors'].append(str(x))); page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None)
   page.route('**/api/ai/capabilities',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps({'executive_brief_available':True,'reason':None})))
   page.route('**/api/ai/summarize',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps({'summary':''})))
   nav=page.goto(f'http://127.0.0.1:{port}/ai-intelligence',wait_until='domcontentloaded')
   page.locator('#ai-file-input').set_input_files(str(pdf)); page.wait_for_function("!document.querySelector('#ai-active-doc-bar')?.hidden")
   page.locator('#trigger-summary-btn').click(); page.wait_for_function("document.querySelector('#summary-display')?.querySelector('[role=alert]')")
   before=page.locator('#summary-display').inner_text()
   page.locator('#ai-clear-doc-btn').click(); page.wait_for_timeout(300)
   after=page.locator('#summary-display').inner_text()
   e.update({'route_status':nav.status if nav else None,'failure_text_before_clear':before,'summary_after_clear':after,'doc_bar_hidden':page.locator('#ai-active-doc-bar').is_hidden(),'stale_error_after_clear':page.locator('#summary-display [role=alert]').count()>0,'viewport':[390,844]})
   page.screenshot(path=str(OUT.parent/'browser-id225-clear-summary-error.png'),full_page=True); browser.close()
 finally:
  app.terminate()
  try: app.wait(timeout=5)
  except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
e['passed']=bool(e.get('route_status')==200 and e.get('failure_text_before_clear') and e.get('doc_bar_hidden') and not e.get('stale_error_after_clear') and not e['page_errors'] and not e['console_errors'])
OUT.write_text(json.dumps(e,indent=2),encoding='utf-8'); print(json.dumps(e,indent=2))
if not e['passed']: raise SystemExit(1)

