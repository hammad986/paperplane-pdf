from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/launch-audit-v24/browser-py312-corrupt-upload-regression.json'
CI_PY = Path(__import__('tempfile').gettempdir()) / 'paperplane-ci-py312-v24' / 'Scripts' / 'python.exe'
sys.path.insert(0, str(ROOT))

def start_ci_server(data):
  with socket.socket() as candidate:
    candidate.bind(('127.0.0.1', 0)); port = candidate.getsockname()[1]
  env={name:value for name,value in os.environ.items() if not name.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and name not in {'TESTING','SESSION_SECRET_KEY'}}
  env.update(PAPERPLANE_SKIP_DOTENV='1', PAPERPLANE_ENV='development', PAPERPLANE_DATA_DIR=str(data), PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(30), PAPERPLANE_PORT=str(port), PYTHONPATH=str(ROOT), PAPERPLANE_SECURE_COOKIES='false')
  return subprocess.Popen([str(CI_PY),'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL),f'http://127.0.0.1:{port}'

def main():
  with TemporaryDirectory(prefix='paperplane-v24-corrupt-upload-') as tmp:
    data=Path(tmp)/'data'; app,base=start_ci_server(data)
    result={'candidate':'Python 3.12 isolated local server; installed Google Chrome via Playwright','cases':[],'page_errors':[],'console_errors':[],'expected_http_error_console_entries':[]}
    try:
      port=int(base.rsplit(':',1)[1])
      for _ in range(120):
        try:
          with socket.create_connection(('127.0.0.1',port),timeout=.2): break
        except OSError: time.sleep(.15)
      else: raise RuntimeError('local app did not start')
      with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(); page.on('pageerror',lambda err:result['page_errors'].append(str(err).splitlines()[0][:200]))
        page.on('console',lambda msg: (result['expected_http_error_console_entries'] if 'responded with a status of 422' in msg.text else result['console_errors']).append(msg.text[:200]) if msg.type=='error' else None)
        response=page.goto(base+'/rotate-pdf',wait_until='domcontentloaded'); assert response and response.status==200
        result['cases']=page.evaluate('''async()=>{const bad=new Blob(['%PDF-1.7\\nnot a parseable PDF'],{type:'application/pdf'});const inspect=new FormData();inspect.append('file',bad,'corrupt.pdf');const a=await fetch('/api/studio/security/inspect',{method:'POST',body:inspect});const ab=await a.json();const job=new FormData();job.append('operation','rotate');job.append('options','{}');job.append('files',bad,'corrupt.pdf');const b=await fetch('/api/jobs',{method:'POST',body:job});const bb=await b.json();return[{name:'studio_security_inspect',status:a.status,detail:ab.detail},{name:'job_upload',status:b.status,detail:bb.detail}]}''')
        browser.close()
      time.sleep(.2); entries=list((data/'jobs').glob('*')) if (data/'jobs').exists() else []
      result['rejected_job_temp_entries']=[p.name for p in entries]
      result['result']='passed' if all(c['status']==422 and 'damaged or unreadable' in c['detail'] for c in result['cases']) and not entries and not result['page_errors'] and not result['console_errors'] and len(result['expected_http_error_console_entries'])==2 else 'failed'
      OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
      if result['result']!='passed': raise SystemExit(1)
    finally:
      app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
