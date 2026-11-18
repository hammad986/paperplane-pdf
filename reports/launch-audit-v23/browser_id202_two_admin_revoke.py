from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, secrets, socket, subprocess, sys, time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23'
with TemporaryDirectory(prefix='paperplane-id202-two-admin-') as tmp:
 data_dir=Path(tmp)/'data'
 with socket.socket() as candidate:candidate.bind(('127.0.0.1',0));port=candidate.getsockname()[1]
 env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}
 env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(data_dir),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(64),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(30),'PAPERPLANE_PORT':str(port),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT),'TESTING':'True'})
 seed="""import json,secrets; from persistence import init_db,create_admin_session; init_db(); from server import PRIMARY_ADMIN_EMAIL,ADMIN_OWNER_EMAILS; emails=sorted(ADMIN_OWNER_EMAILS); print(json.dumps({'sessions':[(e,create_admin_session(e)) for e in emails]}))"""
 seeded=subprocess.run([sys.executable,'-c',seed],cwd=ROOT,env=env,text=True,capture_output=True,check=True)
 admins=json.loads(seeded.stdout)['sessions'];assert len(admins)==2
 app=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  results=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);actor,target=admins
   page=browser.new_page(viewport={'width':1440,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.add_init_script("sessionStorage.setItem('pp_admin_session',"+json.dumps(actor[1])+")")
   page.goto(f'http://127.0.0.1:{port}/admin',wait_until='domcontentloaded');page.locator('#tab-sessions-btn').wait_for(state='visible')
   page.locator('#tab-sessions-btn').click();page.wait_for_function("document.querySelector('#sessions-tbody')?.querySelectorAll('tr').length===2",timeout=15000)
   before=page.locator('#count-sessions').inner_text();assert before=='2',before
   other=page.locator('#sessions-tbody button[data-session-id]');assert other.count()==1
   target_id=other.get_attribute('data-session-id')
   page.once('dialog',lambda d:d.accept());other.click()
   page.wait_for_function("document.querySelector('#sessions-tbody')?.querySelectorAll('tr').length===1",timeout=10000)
   revoked=page.evaluate("async token=>{const r=await fetch('/api/admin/dashboard',{headers:{'X-Admin-Session':token},cache:'no-store'});return r.status}",target[1])
   current=page.evaluate("async token=>{const r=await fetch('/api/admin/dashboard',{headers:{'X-Admin-Session':token},cache:'no-store'});return r.status}",actor[1])
   assert revoked==401 and current==200,(revoked,current);assert not errors,errors
   results.append({'two_owner_sessions_visible':int(before),'other_session_button_clicked':True,'remaining_session_count':1,'revoked_other_session_status':revoked,'current_owner_status':current,'page_errors':errors})
   page.screenshot(path=str(OUT/'id202-two-admin-sessions.png'));browser.close()
  (OUT/'browser-id202-two-admin-revoke.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
 finally:app.terminate();app.wait(timeout=5)
