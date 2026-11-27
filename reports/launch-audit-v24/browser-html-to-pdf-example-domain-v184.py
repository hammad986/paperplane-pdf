from __future__ import annotations
import json, os, secrets, socket, subprocess, time
from pathlib import Path
from urllib.request import urlopen
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
CONTAINER='paperplane-v24-html-public-url'; PORT=18585; BASE=f'http://127.0.0.1:{PORT}'; IMAGE='pdf_splitter-paperplane:latest'
for line in (["docker","ps","-aq","--filter",f"name=^{CONTAINER}$"],):
 if subprocess.run(line,capture_output=True,text=True).stdout.strip(): raise RuntimeError('refusing existing test container')
with socket.socket() as s:
 s.bind(('127.0.0.1',PORT))
admin=secrets.token_urlsafe(48); code=secrets.token_urlsafe(32); session=secrets.token_urlsafe(48)
run=subprocess.run(['docker','run','-d','--name',CONTAINER,'--restart=no','--cpus=4','--memory=4g','--pids-limit=1024','--security-opt=no-new-privileges','-p',f'127.0.0.1:{PORT}:8501','--tmpfs','/data:rw,nosuid,nodev,size=512m','--tmpfs','/tmp:rw,nosuid,nodev,size=256m','-e','PAPERPLANE_ENV=production','-e','PAPERPLANE_SKIP_DOTENV=1','-e','PAPERPLANE_WORKERS=4','-e','PAPERPLANE_DATA_DIR=/data','-e','PAPERPLANE_PORT=8501','-e','PAPERPLANE_PUBLIC_URL=https://paperplane.example.test','-e','PAPERPLANE_SECURE_COOKIES=false','-e','PAPERPLANE_ADMIN_KEY='+admin,'-e','PAPERPLANE_ADMIN_CODE='+code,'-e','PAPERPLANE_SESSION_SECRET='+session,'-e','CASHFREE_ENV=TEST',IMAGE],capture_output=True,text=True,check=True)
evidence={'image':IMAGE,'container_id':run.stdout.strip(),'base':BASE,'target_url':'https://example.com/','provider_credentials':False,'real_payment':False,'page_errors':[],'console_errors':[]}
try:
 for _ in range(90):
  try:
   with urlopen(BASE+'/api/health',timeout=2) as response:
    health=json.loads(response.read())
    if response.status==200 and health.get('status')=='ok':break
  except Exception:time.sleep(1)
 else:raise RuntimeError('container health did not become ok')
 seed="from persistence import create_user,get_user_by_email,set_user_tier; row=get_user_by_email('audit-html-url@example.invalid'); uid=row['id'] if row else create_user('audit-html-url@example.invalid','Dummy-Password-Only!'); set_user_tier(uid,'pro'); print('seeded')"
 subprocess.run(['docker','exec',CONTAINER,'python','-c',seed],capture_output=True,text=True,check=True,timeout=30)
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='chrome',headless=True); context=browser.new_context(viewport={'width':1366,'height':900}); page=context.new_page()
  page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
  page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
  page.goto(BASE+'/html-to-pdf',wait_until='domcontentloaded')
  login=page.request.post(BASE+'/api/auth/login',data={'email':'audit-html-url@example.invalid','password':'Dummy-Password-Only!'},headers={'content-type':'application/json'})
  assert login.status==200,login.text()
  assert page.request.get(BASE+'/api/auth/me').json().get('email')=='audit-html-url@example.invalid'
  opts=json.dumps({'url':'https://example.com/'})
  start=page.request.post(BASE+'/api/jobs',multipart={'operation':'html_to_pdf','options':opts})
  assert start.status in (200,202),f'{start.status} {start.text()}'
  body=start.json(); status_url=BASE+body.get('status_url',f"/api/jobs/{body.get('job_id')}")
  state=None
  for _ in range(180):
   time.sleep(1); response=page.request.get(status_url); assert response.status==200,(response.status,response.text()); state=response.json()
   if state.get('status') in ('completed','failed'):break
  assert state and state.get('status')=='completed',state
  download_url=BASE+state.get('download_url',body.get('download_url',''))
  downloaded=page.request.get(download_url); assert downloaded.status==200,downloaded.status
  data=downloaded.body(); output=OUT/'browser-html-to-pdf-example-domain-v184.pdf'; output.write_bytes(data)
  doc=fitz.open(stream=data,filetype='pdf'); text='\n'.join(x.get_text() for x in doc); pages=len(doc); doc.close()
  assert data.startswith(b'%PDF-') and pages>=1 and 'Example Domain' in text,(len(data),pages,text[:500])
  evidence.update({'health':health,'job_status':state.get('status'),'output_name':state.get('output_name'),'output_bytes':len(data),'pdf_signature':data[:8].decode('ascii','replace'),'page_count':pages,'example_domain_text_found':True,'text_sample':text[:400],'result':'passed'})
  assert not evidence['page_errors']; assert not evidence['console_errors'],evidence['console_errors']; browser.close()
finally:
 logs=subprocess.run(['docker','logs',CONTAINER],capture_output=True,text=True,timeout=20)
 (OUT/'browser-html-to-pdf-example-domain-v184-container.log').write_text(logs.stdout+'\n--- STDERR ---\n'+logs.stderr,encoding='utf-8')
 subprocess.run(['docker','stop','--time','10',CONTAINER],capture_output=True,timeout=30)
 subprocess.run(['docker','rm','--force',CONTAINER],capture_output=True,timeout=30)
(OUT/'browser-html-to-pdf-example-domain-v184.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))

