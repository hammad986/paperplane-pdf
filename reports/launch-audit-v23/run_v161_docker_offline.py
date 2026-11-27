"""Run current-candidate Docker offline PWA Chromium smoke with a disposable container."""
from __future__ import annotations
import json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
IMAGE='paperplane-v23-audit:codex-v161'; NAME='paperplane-v23-v161-offline'; PORT=18563; BASE=f'http://127.0.0.1:{PORT}'
def run(args,timeout=60): return subprocess.run(args,check=True,text=True,capture_output=True,timeout=timeout)
if run(['docker','ps','-aq','--filter',f'name=^{NAME}$']).stdout.strip(): raise RuntimeError('refusing existing container')
with socket.socket() as probe:
 if probe.connect_ex(('127.0.0.1',PORT))==0: raise RuntimeError(f'refusing occupied port {PORT}')
admin=secrets.token_urlsafe(48); code=secrets.token_urlsafe(32); session=secrets.token_urlsafe(48); started=False
try:
 run(['docker','run','-d','--name',NAME,'--restart=no','--cpus=4','--memory=4g','--pids-limit=128','--security-opt=no-new-privileges',
      '-p',f'127.0.0.1:{PORT}:8501','--tmpfs','/data:rw,nosuid,nodev,size=256m','--tmpfs','/tmp:rw,nosuid,nodev,size=128m',
      '-e','PAPERPLANE_ENV=production','-e','PAPERPLANE_SKIP_DOTENV=1','-e','PAPERPLANE_WORKERS=4','-e','PAPERPLANE_DATA_DIR=/data','-e','PAPERPLANE_PORT=8501',
      '-e','PAPERPLANE_PUBLIC_URL=https://paperplane.example.test','-e','PAPERPLANE_SECURE_COOKIES=false','-e','PAPERPLANE_JOB_TTL_SECONDS=86400',
      '-e',f'PAPERPLANE_ADMIN_KEY={admin}','-e',f'PAPERPLANE_ADMIN_CODE={code}','-e',f'PAPERPLANE_SESSION_SECRET={session}',
      '-e','ADMIN_ALERT_EMAIL=audit@example.invalid','-e','CASHFREE_ENV=TEST',IMAGE]); started=True
 health=None
 for _ in range(90):
  try:
   with urlopen(BASE+'/api/health',timeout=2) as r:
    health=json.loads(r.read())
    if r.status==200 and health.get('status')=='ok': break
  except Exception: time.sleep(1)
 if not health or health.get('status')!='ok': raise RuntimeError('image health failed')
 uid=run(['docker','exec',NAME,'cat','/proc/1/status']).stdout
 uid_line=next(x for x in uid.splitlines() if x.startswith('Uid:')); uids=[int(x) for x in uid_line.split()[1:5]]
 if uids!=[1001]*4: raise RuntimeError(f'UID mismatch: {uids}')
 image_id=run(['docker','image','inspect',IMAGE,'--format','{{.Id}}']).stdout.strip()
 env=os.environ.copy(); env.update({'PAPERPLANE_DOCKER_BASE':BASE,'PAPERPLANE_DOCKER_IMAGE_ID':image_id})
 browser=subprocess.run([sys.executable,str(OUT/'browser_v161_docker_offline_pwa.py')],cwd=ROOT,env=env,text=True,capture_output=True,timeout=180)
 (OUT/'browser-v161-docker-offline-pwa-run.log').write_text(browser.stdout+browser.stderr,encoding='utf-8')
 if browser.returncode: raise RuntimeError('offline browser smoke failed; inspect browser-v161-docker-offline-pwa-run.log')
 studio_env=os.environ.copy(); studio_env.update({
     'PAPERPLANE_TEST_BASE':BASE,
     'PAPERPLANE_EVIDENCE_SUFFIX':'_docker_v161',
     'PAPERPLANE_TEST_ROUNDS':'1,2',
 })
 studio=subprocess.run([sys.executable,str(OUT/'browser_id122_mobile_69page_studio_export.py')],
                       cwd=ROOT,env=studio_env,text=True,capture_output=True,timeout=300)
 (OUT/'browser-id122-v161-docker-studio-run.log').write_text(studio.stdout+studio.stderr,encoding='utf-8')
 if studio.returncode: raise RuntimeError('v161 Docker 69-page Studio browser check failed; inspect browser-id122-v161-docker-studio-run.log')
 report={'image':IMAGE,'image_id':image_id,'health':health,'process_uids':uids,'browser_exit':browser.returncode,
         'browser_evidence':'browser-v161-docker-offline-pwa.json','studio_browser_exit':studio.returncode,
         'studio_browser_evidence':'browser-id122-mobile-69page-studio-export_docker_v161.json',
         'runtime':'isolated container stopped and removed','ttl_override_seconds':86400}
 (OUT/'docker-v161-runtime.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
finally:
 if started:
  subprocess.run(['docker','stop','--time','10',NAME],check=False,text=True,capture_output=True,timeout=30)
  subprocess.run(['docker','rm','--force',NAME],check=False,text=True,capture_output=True,timeout=30)
print(json.dumps(report,indent=2))
