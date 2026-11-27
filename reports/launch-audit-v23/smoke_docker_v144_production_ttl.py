"""Read-only current-image smoke for the production job-retention override."""
from __future__ import annotations
import json, secrets, socket, subprocess, time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
IMAGE='paperplane-v23-audit:codex-v144'
CONTAINER='paperplane-v23-v144-ttl-smoke'
PORT=18510
BASE=f'http://127.0.0.1:{PORT}'

def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)

existing=run(['docker','ps','-aq','--filter',f'name=^{CONTAINER}$']).stdout.strip()
if existing: raise RuntimeError(f'Refusing to replace pre-existing container {CONTAINER}')
with socket.socket() as probe:
    if probe.connect_ex(('127.0.0.1',PORT))==0: raise RuntimeError(f'Refusing occupied port {PORT}')
admin=secrets.token_urlsafe(48)
admin_code=secrets.token_urlsafe(32)
session=secrets.token_urlsafe(48)
started=False
try:
    run(['docker','run','-d','--name',CONTAINER,'--restart=no','--cpus=4','--memory=2g','--pids-limit=128',
         '--security-opt=no-new-privileges','-p',f'127.0.0.1:{PORT}:8501',
         '--tmpfs','/data:rw,nosuid,nodev,size=128m','--tmpfs','/tmp:rw,nosuid,nodev,size=128m',
         '-e','PAPERPLANE_ENV=production','-e','PAPERPLANE_SKIP_DOTENV=1','-e','PAPERPLANE_WORKERS=4',
         '-e','PAPERPLANE_DATA_DIR=/data','-e','PAPERPLANE_PORT=8501',
         '-e','PAPERPLANE_PUBLIC_URL=https://paperplane.example.test','-e','PAPERPLANE_SECURE_COOKIES=false',
         '-e',f'PAPERPLANE_ADMIN_KEY={admin}','-e',f'PAPERPLANE_ADMIN_CODE={admin_code}',
         '-e',f'PAPERPLANE_SESSION_SECRET={session}','-e','PAPERPLANE_JOB_TTL_SECONDS=86400',
         '-e','ADMIN_ALERT_EMAIL=audit@example.invalid','-e','CASHFREE_ENV=TEST',IMAGE])
    started=True
    health=None
    for _ in range(90):
        try:
            with urlopen(BASE+'/api/health',timeout=2) as response:
                health={'http_status':response.status,**json.loads(response.read())}
                if response.status==200 and health.get('status')=='ok': break
        except Exception: time.sleep(1)
    if not health or health.get('status')!='ok': raise RuntimeError('health endpoint did not become healthy')
    if health.get('job_ttl_hours')!=24 or health.get('workers')!=4:
        raise RuntimeError(f'production override mismatch: {health}')
    status=run(['docker','exec',CONTAINER,'cat','/proc/1/status']).stdout
    uid_line=next(line for line in status.splitlines() if line.startswith('Uid:'))
    uids=[int(x) for x in uid_line.split()[1:5]]
    if uids != [1001]*4: raise RuntimeError(f'UID-1001 app process invariant failed: {uids}')
    image_id=run(['docker','image','inspect',IMAGE,'--format','{{.Id}}']).stdout.strip()
    result={'image':IMAGE,'image_id':image_id,'health':health,'process_uids':uids,
            'ttl_override_seconds':86400,'runtime':'isolated production-mode container, tmpfs only',
            'synthetic_secrets_only':True,'payment_attempted':False,'provider_credentials_used':False,
            'container':'stopped and removed after health smoke'}
    (OUT/'docker-v144-production-ttl-override.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
finally:
    if started:
        subprocess.run(['docker','stop','--time','10',CONTAINER],check=False,capture_output=True,text=True,timeout=30)
        subprocess.run(['docker','rm','--force',CONTAINER],check=False,capture_output=True,text=True,timeout=30)
print(json.dumps(result,indent=2))
