"""Run the 44-operation Chromium catalog on disposable current v165 image."""
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
IMAGE = "paperplane-v23-audit:codex-v165"
CONTAINER = "paperplane-v23-v165-catalog"
PORT = 18565
BASE = f"http://127.0.0.1:{PORT}"
SUFFIX = "-current-v165-2026-11-22"
EVIDENCE = OUT / f"browser-id28-v165-current-image-catalog{SUFFIX}.json"
RUNTIME = OUT / f"docker-v165-current-catalog-runtime.json"


def run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
    raise RuntimeError(f"Current candidate image is missing: {IMAGE}")
if subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"], capture_output=True, text=True).stdout.strip():
    raise RuntimeError(f"Refusing existing container {CONTAINER}")
with __import__("socket").socket() as probe:
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        raise RuntimeError(f"Refusing occupied port {PORT}")

admin = secrets.token_urlsafe(48)
code = secrets.token_urlsafe(32)
session = secrets.token_urlsafe(48)
started = False
try:
    run([
        "docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=4", "--memory=4g",
        "--pids-limit=128", "--security-opt=no-new-privileges", "-p", f"127.0.0.1:{PORT}:8501",
        "--tmpfs", "/data:rw,nosuid,nodev,size=512m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
        "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1", "-e", "PAPERPLANE_WORKERS=4",
        "-e", "PAPERPLANE_DATA_DIR=/data", "-e", "PAPERPLANE_PORT=8501",
        "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test", "-e", "PAPERPLANE_SECURE_COOKIES=false",
        "-e", "PAPERPLANE_JOB_TTL_SECONDS=86400", "-e", f"PAPERPLANE_ADMIN_KEY={admin}",
        "-e", f"PAPERPLANE_ADMIN_CODE={code}", "-e", f"PAPERPLANE_SESSION_SECRET={session}",
        "-e", "ADMIN_ALERT_EMAIL=audit@example.invalid", "-e", "CASHFREE_ENV=TEST", IMAGE,
    ])
    started = True
    health = None
    for _ in range(90):
        try:
            with urlopen(BASE + "/api/health", timeout=2) as response:
                health = json.loads(response.read())
                if response.status == 200 and health.get("status") == "ok":
                    break
        except Exception:
            time.sleep(1)
    if not health or health.get("status") != "ok":
        raise RuntimeError("current v165 production image failed health check")

    image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip()
    env = os.environ.copy()
    env.update({
        "PAPERPLANE_AUDIT_SUFFIX": SUFFIX,
        "PAPERPLANE_AUDIT_BASE": BASE,
        "PAPERPLANE_AUDIT_CONTAINER": CONTAINER,
        "PAPERPLANE_AUDIT_DATA_DIR": str(OUT / "runtime-id28-current-v165"),
    })
    result = subprocess.run(
        [sys.executable, str(OUT / "browser_id28_v165_docker_catalog.py")],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=1500,
    )
    (OUT / f"browser-id28-current-v165-catalog.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("current v165 operation catalog failed; inspect browser-id28-current-v165-catalog.log")
    RUNTIME.write_text(json.dumps({
        "image": IMAGE, "image_id": image_id, "health": health, "catalog_exit_code": result.returncode,
        "catalog_evidence": EVIDENCE.name, "catalog_log": "browser-id28-current-v165-catalog.log",
        "storage": "temporary container with tmpfs only", "real_payment": False, "provider_credentials": False,
    }, indent=2), encoding="utf-8")
finally:
    if started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, capture_output=True, timeout=30)

print(json.dumps({"image": IMAGE, "health": health, "evidence": str(EVIDENCE), "runtime": str(RUNTIME)}, indent=2))
