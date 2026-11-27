from __future__ import annotations
import json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'/'launch-audit-v24'/'browser-id243-api-key-plan-gate.json'

def clean_env():
 return {k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}

def main():
 evidence={'accounts':[],'page_errors':[],'console_errors':[],'production_or_payment_endpoints_contacted':False}
 with TemporaryDirectory(prefix='paperplane-v24-id243-') as tmp:
  root=Path(tmp);data=root/'data'
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  env=clean_env();env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(data),'PAPERPLANE_PORT':str(port),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(48),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(32),'PAPERPLANE_SESSION_SECRET':secrets.token_urlsafe(48),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT),'PYTHONIOENCODING':'utf-8'})
  seed="from persistence import init_db,create_user,create_session_for_user,set_user_tier;import json;init_db();out=[];\nfor tier in ('free','student_pro'):\n email='id243-'+tier+'@example.invalid';uid=create_user(email,'Synthetic-Id243-Only!');set_user_tier(uid,tier);out.append({'tier':tier,'token':create_session_for_user(uid)['token']})\nprint(json.dumps(out))"
  accounts=json.loads(subprocess.run([sys.executable,'-c',seed],cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=30).stdout)
  app=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   for _ in range(150):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2):break
    except OSError:time.sleep(.2)
   else:raise RuntimeError('local app did not start')
   base=f'http://127.0.0.1:{port}'
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for account in accounts:
     context=browser.new_context(viewport={'width':1366,'height':900})
     context.add_cookies([{'name':'paperplane_token','value':account['token'],'url':base,'httpOnly':True,'secure':False,'sameSite':'Lax'}])
     page=context.new_page();page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)));page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
     page.goto(base+'/settings',wait_until='domcontentloaded')
     page.wait_for_function('(tier)=>window.state?.user?.tier===tier',arg=account['tier'],timeout=15000)
     page.locator(".settings-tab-btn[data-tab='api']").click()
     form=page.locator('#settings-create-key-form');hint=page.locator('#settings-api-key-upgrade-hint')
     assert form.is_hidden() and hint.is_visible(),{'tier':account['tier'],'form_hidden':form.is_hidden(),'hint_visible':hint.is_visible()}
     denied=page.request.post(base+'/api/developer/keys',data={'name':'must-not-exist'},headers={'content-type':'application/x-www-form-urlencoded'})
     assert denied.status==403,{'tier':account['tier'],'status':denied.status,'body':denied.text()}
     evidence['accounts'].append({'tier':account['tier'],'generate_form_hidden':True,'upgrade_hint_visible':True,'direct_api_post_status':denied.status,'key_material_returned':False})
     context.close()
    browser.close()
  finally:
   app.terminate()
   try:app.wait(timeout=5)
   except Exception:app.kill();app.wait(timeout=5)
 evidence['passed']=len(evidence['accounts'])==2 and all(a['direct_api_post_status']==403 and a['generate_form_hidden'] for a in evidence['accounts']) and not evidence['page_errors'] and not evidence['console_errors']
 OUT.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2))
 if not evidence['passed']:raise SystemExit(1)
if __name__=='__main__':main()
