from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGE = "paperplane-v23-audit:codex-v150"
CONTAINER = "paperplane-v23-v150-id37-smoke"
BASE = "http://127.0.0.1:18521"


def run(args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=timeout)


image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip()
existing = run(["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"]).stdout.strip()
if existing:
    raise RuntimeError(f"Refusing to replace existing container {CONTAINER}")

args = [
    "docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=4", "--memory=4g",
    "--pids-limit=128", "--security-opt=no-new-privileges", "-p", "127.0.0.1:18521:8501",
    "--tmpfs", "/data:rw,nosuid,nodev,size=512m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
    "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1",
    "-e", "PAPERPLANE_WORKERS=4", "-e", "PAPERPLANE_DATA_DIR=/data", "-e", "PAPERPLANE_PORT=8501",
    "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test", "-e", "PAPERPLANE_SECURE_COOKIES=false",
    "-e", f"PAPERPLANE_ADMIN_KEY={secrets.token_urlsafe(64)}",
    "-e", f"PAPERPLANE_ADMIN_CODE={secrets.token_urlsafe(32)}",
    "-e", f"PAPERPLANE_SESSION_SECRET={secrets.token_urlsafe(64)}",
    "-e", "ADMIN_ALERT_EMAIL=audit@example.invalid", "-e", "CASHFREE_ENV=TEST", IMAGE,
]
started = False
health = None
browser_results = []
try:
    run(args)
    started = True
    for _ in range(120):
        try:
            with urlopen(BASE + "/api/health", timeout=2) as response:
                health = json.loads(response.read())
                if response.status == 200 and health.get("status") == "ok":
                    break
        except Exception:
            time.sleep(1)
    if not health or health.get("status") != "ok":
        raise RuntimeError("v150 production-mode container did not become healthy")

    env = os.environ.copy()
    env.update({"PAPERPLANE_TEST_BASE": BASE, "PAPERPLANE_TEST_RUNTIME": "v150-docker"})
    for script in ("browser_id37_processing_disclosure.py", "browser_id37_local_pdf_to_word.py"):
        result = subprocess.run([sys.executable, str(OUT / script)], cwd=ROOT, env=env,
                                text=True, capture_output=True, timeout=180)
        evidence_name = ("browser-id37-processing-disclosure-v150-docker.json"
                         if "disclosure" in script else "browser-id37-local-pdf-to-word-v150-docker.json")
        browser_results.append({"script": script, "exit_code": result.returncode, "evidence": evidence_name})
        (OUT / f"{Path(script).stem}-v150-docker.log").write_text(
            result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{script} failed; inspect its v150-docker log")

    runtime = {
        "image": IMAGE,
        "image_id": image_id,
        "health": health,
        "container_status": "healthy then stopped and removed",
        "browser_results": browser_results,
        "storage": "disposable tmpfs",
        "synthetic_credentials": True,
        "provider_credentials": False,
        "real_payment": False,
    }
    (OUT / "docker-id37-v150-runtime.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    print(json.dumps(runtime, indent=2))
finally:
    if started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False,
                       text=True, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False,
                       text=True, capture_output=True, timeout=30)
