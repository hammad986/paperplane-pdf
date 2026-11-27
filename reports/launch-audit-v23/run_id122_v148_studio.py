"""Run 69-page Studio browser acceptance on disposable current image v148."""
from __future__ import annotations
import json, os, secrets, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
IMAGE='paperplane-v23-audit:codex-v148'
CONTAINER='paperplane-v23-v148-studio'
BASE='http://127.0.0.1:18520'
RUNTIME=OUT/'docker-id122-v148-studio-runtime.json'
LOG=OUT/'browser-id122-v148-studio.log'

def run(args, **kwargs):
    return subprocess.run(args,check=True,text=True,capture_output=True,**kwargs)

image_id=run(['docker','image','inspect',IMAGE,'--format','{{.Id}}']).stdout.strip()
if image_id!='sha256:7e4a1db49661f38cf4f9d5230e565dce119c40693dec092f9add43072ab444d0':
    raise RuntimeError(f'Unexpected v148 image id: {image_id}')
existing=run(['docker','ps','-aq','--filter',f'name=^{CONTAINER}$']).stdout.strip()
if existing: raise RuntimeError(f'Refusing to replace pre-existing container {CONTAINER}')
args=['docker','run','-d','--name',CONTAINER,'--restart=no','--cpus=4','--memory=4g','--pids-limit=128',
      '--security-opt=no-new-privileges','-p','127.0.0.1:18520:8501',
      '--tmpfs','/data:rw,nosuid,nodev,size=512m','--tmpfs','/tmp:rw,nosuid,nodev,size=256m',
      '-e','PAPERPLANE_ENV=production','-e','PAPERPLANE_SKIP_DOTENV=1','-e','PAPERPLANE_WORKERS=4',
      '-e','PAPERPLANE_DATA_DIR=/data','-e','PAPERPLANE_PORT=8501','-e','PAPERPLANE_PUBLIC_URL=https://paperplane.example.test',
      '-e','PAPERPLANE_SECURE_COOKIES=false','-e',f'PAPERPLANE_ADMIN_KEY={secrets.token_urlsafe(64)}',
      '-e',f'PAPERPLANE_ADMIN_CODE={secrets.token_urlsafe(32)}','-e',f'PAPERPLANE_SESSION_SECRET={secrets.token_urlsafe(64)}',
      '-e','ADMIN_ALERT_EMAIL=audit@example.invalid','-e','CASHFREE_ENV=TEST',IMAGE]
started=False
try:
    run(args); started=True
    health=None
    for _ in range(120):
        try:
            with urlopen(BASE+'/api/health',timeout=2) as response:
                health=json.loads(response.read())
                if response.status==200 and health.get('status')=='ok': break
        except Exception: time.sleep(1)
    if not health or health.get('status')!='ok': raise RuntimeError('v148 Studio container health failed')
    env=os.environ.copy(); env['PAPERPLANE_TEST_IMAGE_TAG']=IMAGE
    result=subprocess.run([sys.executable,str(OUT/'browser_id122_docker_studio_smoke_v148.py')],cwd=ROOT,env=env,text=True,capture_output=True,timeout=900)
    LOG.write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode: raise RuntimeError(f'69-page browser test failed, inspect {LOG.name}')
    RUNTIME.write_text(json.dumps({'image':IMAGE,'image_id':image_id,'health':health,'browser_exit_code':result.returncode,
      'browser_log':LOG.name,'container_status':'healthy then stopped','storage':'tmpfs only','provider_credentials':False,
      'real_payment':False},indent=2),encoding='utf-8')
finally:
    if started:
        subprocess.run(['docker','stop','--time','10',CONTAINER],check=False,text=True,capture_output=True,timeout=30)
        subprocess.run(['docker','rm','--force',CONTAINER],check=False,text=True,capture_output=True,timeout=30)
print(json.dumps({'image_id':image_id,'health':health,'browser_exit_code':result.returncode if 'result' in locals() else None,
 'runtime':str(RUNTIME),'browser_log':str(LOG)},indent=2))
