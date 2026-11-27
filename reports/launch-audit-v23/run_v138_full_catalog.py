"""Run another isolated, disposable two-round ID 28 Docker catalog pass."""
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
IMAGE = "paperplane-v23-audit:codex-v138"
EXPECTED_IMAGE_ID = "sha256:79d24d51f249bc55bd23958997bf9e51361d853e541f980eafe7ca8dc9bcb7ea"
CONTAINER = "paperplane-v23-v138-catalog"
BASE = "http://127.0.0.1:18508"
SUFFIX = "-catalog-v138-2026-11-20"
EVIDENCE = OUT / f"browser-id28-v138-current-image-catalog{SUFFIX}.json"
RUNTIME = OUT / f"docker-id28-v138-runtime{SUFFIX}.json"


def run(args: list[str], *, timeout: int = 60, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=capture, timeout=timeout)


image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip()
if image_id != EXPECTED_IMAGE_ID:
    raise RuntimeError(f"Refusing unexpected image digest: {image_id}")
existing = subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"], check=True, text=True, capture_output=True).stdout.strip()
if existing:
    raise RuntimeError(f"Refusing to replace pre-existing container {CONTAINER}")

admin_key = secrets.token_urlsafe(64)
admin_code = secrets.token_urlsafe(32)
session_secret = secrets.token_urlsafe(64)
docker_args = [
    "docker", "run", "-d", "--name", CONTAINER,
    "--restart=no", "--cpus=4", "--memory=4g", "--pids-limit=128",
    "--security-opt=no-new-privileges",
    "-p", "127.0.0.1:18508:8501",
    "--tmpfs", "/data:rw,nosuid,nodev,size=512m",
    "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
    "-e", "PAPERPLANE_ENV=production",
    "-e", "PAPERPLANE_SKIP_DOTENV=1",
    "-e", "PAPERPLANE_WORKERS=4",
    "-e", "PAPERPLANE_DATA_DIR=/data",
    "-e", "PAPERPLANE_PORT=8501",
    "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test",
    "-e", "PAPERPLANE_SECURE_COOKIES=false",
    "-e", f"PAPERPLANE_ADMIN_KEY={admin_key}",
    "-e", f"PAPERPLANE_ADMIN_CODE={admin_code}",
    "-e", f"PAPERPLANE_SESSION_SECRET={session_secret}",
    "-e", "ADMIN_ALERT_EMAIL=audit@example.invalid",
    "-e", "CASHFREE_ENV=TEST",
    IMAGE,
]
started = False
try:
    run(docker_args)
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
        logs = subprocess.run(["docker", "logs", CONTAINER], check=False, text=True, capture_output=True)
        state = subprocess.run(["docker", "inspect", CONTAINER, "--format", "{{json .State}}"], check=False, text=True, capture_output=True)
        raise RuntimeError(
            f"Disposable runtime health failed; container_state={state.stdout.strip()}; "
            f"stdout_tail={logs.stdout[-2000:]}; stderr_tail={logs.stderr[-4000:]}"
        )

    child_env = os.environ.copy()
    child_env.update({
        "PAPERPLANE_AUDIT_SUFFIX": SUFFIX,
        "PAPERPLANE_AUDIT_BASE": BASE,
        "PAPERPLANE_AUDIT_CONTAINER": CONTAINER,
    })
    catalog = subprocess.run(
        [sys.executable, str(OUT / "browser_id28_v138_docker_catalog.py")],
        cwd=ROOT, env=child_env, text=True, capture_output=True, timeout=1500,
    )
    (OUT / f"browser-id28-current-image-continuation{SUFFIX}.log").write_text(
        catalog.stdout + catalog.stderr, encoding="utf-8"
    )
    if catalog.returncode != 0:
        raise RuntimeError(f"Catalog failed (exit {catalog.returncode}); inspect browser-id28-current-image-continuation{SUFFIX}.log")

    runtime = {
        "image": IMAGE,
        "image_id": image_id,
        "container_status": "healthy then stopped",
        "health": health,
        "rounds": 2,
        "catalog_exit_code": catalog.returncode,
        "catalog_evidence": EVIDENCE.name,
        "catalog_log": f"browser-id28-current-image-continuation{SUFFIX}.log",
        "storage": "tmpfs only; disposable synthetic audit account and fixtures",
        "real_payment": False,
        "provider_credentials": False,
    }
    RUNTIME.write_text(json.dumps(runtime, indent=2), encoding="utf-8")
finally:
    if started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, text=True, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, text=True, capture_output=True, timeout=30)

print(json.dumps({"image_id": image_id, "health": health, "catalog_exit_code": catalog.returncode if 'catalog' in locals() else None,
                  "evidence": str(EVIDENCE), "runtime": str(RUNTIME)}, indent=2))

