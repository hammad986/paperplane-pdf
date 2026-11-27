"""Build current source and verify Railway PORT/health host plus browser catalog."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGE = "paperplane-v23-audit:codex-v153-railway-port"
CONTAINER = "paperplane-v23-v153-railway"
PORT = 18528
BASE = f"http://127.0.0.1:{PORT}"
SUFFIX = "-current-v153-railway-2026-11-22"
EVIDENCE = OUT / f"browser-id28-v148-current-image-catalog{SUFFIX}.json"
RUNTIME = OUT / "docker-v153-railway-runtime.json"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0:
    raise RuntimeError(f"Refusing to overwrite existing audit image {IMAGE}")
if subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"], capture_output=True, text=True).stdout.strip():
    raise RuntimeError(f"Refusing existing container {CONTAINER}")
with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        raise RuntimeError(f"Refusing occupied port {PORT}")

build = subprocess.run(["docker", "build", "--tag", IMAGE, str(ROOT)], capture_output=True, text=True, timeout=1800)
(OUT / "docker-build-v153.log").write_text(build.stdout + build.stderr, encoding="utf-8")
if build.returncode:
    raise RuntimeError("Docker build failed; inspect docker-build-v153.log")
admin = secrets.token_urlsafe(48)
code = secrets.token_urlsafe(32)
session = secrets.token_urlsafe(48)
started = False
try:
    run([
        "docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=4", "--memory=4g",
        "--pids-limit=128", "--security-opt=no-new-privileges", "-p", f"127.0.0.1:{PORT}:{PORT}",
        "--tmpfs", "/data:rw,nosuid,nodev,size=512m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
        "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1", "-e", "PAPERPLANE_WORKERS=4",
        "-e", "PAPERPLANE_HOST=0.0.0.0", "-e", f"PORT={PORT}", "-e", "PAPERPLANE_PORT=8501",
        "-e", "RAILWAY_SERVICE_ID=synthetic-railway-service", "-e", "PAPERPLANE_DATA_DIR=/data",
        "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test", "-e", "PAPERPLANE_SECURE_COOKIES=false",
        "-e", "PAPERPLANE_TRUSTED_HOSTS=paperplane.example.test", "-e", "PAPERPLANE_JOB_TTL_SECONDS=86400",
        "-e", f"PAPERPLANE_ADMIN_KEY={admin}", "-e", f"PAPERPLANE_ADMIN_CODE={code}",
        "-e", f"PAPERPLANE_SESSION_SECRET={session}", "-e", "ADMIN_ALERT_EMAIL=audit@example.invalid",
        "-e", "CASHFREE_ENV=TEST", IMAGE,
    ])
    started = True
    health = None
    for _ in range(120):
        try:
            with urlopen(BASE + "/api/health", timeout=2) as response:
                health = json.loads(response.read())
                if response.status == 200 and health.get("status") == "ok":
                    break
        except Exception:
            time.sleep(1)
    if not health or health.get("status") != "ok":
        raise RuntimeError("Railway-style dynamic PORT health request failed")
    with urlopen(Request(BASE + "/api/health", headers={"Host": "healthcheck.railway.app"}), timeout=5) as response:
        railway_health_status = response.status
        if response.status != 200:
            raise RuntimeError(f"Railway health-check Host rejected: HTTP {response.status}")

    image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip()
    env = os.environ.copy()
    env.update({
        "PAPERPLANE_AUDIT_SUFFIX": SUFFIX,
        "PAPERPLANE_AUDIT_BASE": BASE,
        "PAPERPLANE_AUDIT_CONTAINER": CONTAINER,
        "PAPERPLANE_AUDIT_DATA_DIR": str(OUT / "runtime-id28-current-v153"),
    })
    browser = subprocess.run(
        [sys.executable, str(OUT / "browser_id28_v148_docker_catalog.py")],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=1500,
    )
    (OUT / "browser-id28-current-v153-catalog.log").write_text(browser.stdout + browser.stderr, encoding="utf-8")
    if browser.returncode:
        raise RuntimeError("v153 current-image catalog failed; inspect browser-id28-current-v153-catalog.log")
    RUNTIME.write_text(json.dumps({
        "image": IMAGE, "image_id": image_id, "health": health, "railway_health_host_status": railway_health_status,
        "port_environment": {"PORT": PORT, "PAPERPLANE_PORT": 8501}, "catalog_exit_code": browser.returncode,
        "catalog_evidence": EVIDENCE.name, "catalog_log": "browser-id28-current-v153-catalog.log",
        "storage": "temporary container with tmpfs only", "real_payment": False, "provider_credentials": False,
    }, indent=2), encoding="utf-8")
finally:
    if started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, capture_output=True, timeout=30)

print(json.dumps({"image": IMAGE, "health": health, "railway_health_host_status": railway_health_status,
                  "evidence": str(EVIDENCE), "runtime": str(RUNTIME)}, indent=2))
