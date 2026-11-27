from __future__ import annotations
import base64,json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent/'browser-id228-singular-page-toast.json'
with TemporaryDirectory(prefix='paperplane-v24-id228-') as temp:
 tmp=Path(temp); data=tmp/'data'; data.mkdir(); pdf=tmp/'one-page.pdf'
 with fitz.open() as d: d.new_page().insert_text((72,72),'Cloud singular fixture'); d.save(pdf)
 file64=base64.b64encode(pdf.read_bytes()).decode()
 with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
 env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}
 env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(data),'PAPERPLANE_PORT':str(port),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(48),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(32),'PAPERPLANE_SESSION_SECRET':secrets.token_urlsafe(48),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT)})
 app=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); e={'page_errors':[],'console_errors':[]}
 try:
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
   except OSError: time.sleep(.2)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True); page=b.new_page(viewport={'width':1366,'height':900}); page.on('pageerror',lambda x:e['page_errors'].append(str(x))); page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None)
   page.route('**/api/cloud/sync',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps({'data_url':'data:application/pdf;base64,'+file64,'filename':'Sample.pdf'})))
   nav=page.goto(f'http://127.0.0.1:{port}/tool-desk',wait_until='domcontentloaded'); page.locator('#topbar-cloud-btn').click(); page.locator('#cloud-url').fill('https://example.test/one-page.pdf'); page.locator('#cloud-form').evaluate('f=>f.requestSubmit()'); page.wait_for_function("[...document.querySelectorAll('[role=status],.toast,.toast-message')].some(e=>e.innerText.includes('Imported Sample.pdf')) || document.body.innerText.includes('Imported Sample.pdf')",timeout=20000)
   toast=page.get_by_text('Imported Sample.pdf',exact=False).last.inner_text(); e.update({'route_status':nav.status if nav else None,'toast':toast,'correct_singular':'. 1 page' in toast or '· 1 page' in toast,'incorrect_plural':'1 pages' in toast,'active_filename':page.locator('#file-list').inner_text() if page.locator('#file-list').count() else None})
   page.screenshot(path=str(OUT.parent/'browser-id228-singular-page-toast.png'),full_page=True); b.close()
 finally:
  app.terminate()
  try: app.wait(timeout=5)
  except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
e['passed']=bool(e.get('route_status')==200 and e.get('correct_singular') and not e.get('incorrect_plural') and not e['page_errors'] and not e['console_errors']); OUT.write_text(json.dumps(e,indent=2),encoding='utf-8'); print(json.dumps(e,indent=2))
if not e['passed']: raise SystemExit(1)


