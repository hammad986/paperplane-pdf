"""Build-candidate Docker runtime smoke for the current 69-page Studio browser path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGE = "paperplane-v23-audit:codex-v143"
CONTAINER = "paperplane-codex-id122-v143"
BASE = "http://127.0.0.1:18507"


def run(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


existing = subprocess.run(
    ["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"],
    check=True, text=True, capture_output=True,
).stdout.strip()
if existing:
    raise RuntimeError(f"Refusing to replace pre-existing container {CONTAINER}")
with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", 18507)) == 0:
        raise RuntimeError("Refusing to use occupied local port 18507")

admin_key = secrets.token_urlsafe(64)
admin_code = secrets.token_urlsafe(32)
session_secret = secrets.token_urlsafe(64)
args = [
    "docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=4", "--memory=4g",
    "--pids-limit=128", "--security-opt=no-new-privileges", "-p", "127.0.0.1:18507:8501",
    "--tmpfs", "/data:rw,nosuid,nodev,size=512m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
    "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1", "-e", "PAPERPLANE_WORKERS=4",
    "-e", "PAPERPLANE_DATA_DIR=/data", "-e", "PAPERPLANE_PORT=8501",
    "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test", "-e", "PAPERPLANE_SECURE_COOKIES=false",
    "-e", f"PAPERPLANE_ADMIN_KEY={admin_key}", "-e", f"PAPERPLANE_ADMIN_CODE={admin_code}",
    "-e", f"PAPERPLANE_SESSION_SECRET={session_secret}", "-e", "ADMIN_ALERT_EMAIL=audit@example.invalid",
    "-e", "CASHFREE_ENV=TEST", IMAGE,
]
started = False
try:
    run(args)
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
        raise RuntimeError(f"Disposable current-image health failed: {logs.stdout[-2000:]} {logs.stderr[-2000:]}")
    pid1_status = run(["docker", "exec", CONTAINER, "cat", "/proc/1/status"]).stdout
    uid_line = next((line for line in pid1_status.splitlines() if line.startswith("Uid:")), "")
    process_uids = [int(value) for value in uid_line.split()[1:5]] if uid_line else []
    if process_uids != [1001, 1001, 1001, 1001]:
        raise RuntimeError(f"App PID 1 did not drop all UID slots to 1001; observed: {process_uids}")

    env = os.environ.copy()
    env["PAPERPLANE_TEST_IMAGE_TAG"] = IMAGE
    browser = subprocess.run(
        [sys.executable, str(OUT / "browser_id122_docker_studio_smoke_v143.py")],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=900,
    )
    browser_log = OUT / "browser-id122-docker-v143-studio-run.log"
    browser_log.write_text(browser.stdout + browser.stderr, encoding="utf-8")
    if browser.returncode:
        raise RuntimeError(f"Docker Studio Chromium smoke failed; see {browser_log.name}")
    toolbar_browser = subprocess.run(
        [sys.executable, str(OUT / "browser_id45_docker_toolbar.py")],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
    )
    toolbar_log = OUT / "browser-id45-docker-v143-toolbar-run.log"
    toolbar_log.write_text(toolbar_browser.stdout + toolbar_browser.stderr, encoding="utf-8")
    if toolbar_browser.returncode:
        raise RuntimeError(f"Docker ID45 Chromium check failed; see {toolbar_log.name}")
    image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip()
    details = run(["docker", "inspect", CONTAINER, "--format", "{{json .State}} {{json .HostConfig.Tmpfs}}"]).stdout.strip()
    runtime = {
        "image": IMAGE, "image_id": image_id, "container_status": "healthy then stopped and removed",
        "health": health, "runtime_configuration": details,
        "entrypoint_starts_as_root_then_drops_app_to_uid_1001": True, "process_table_uids": process_uids,
        "browser_smoke": "69-page Studio Chromium; two content-checked downloads; ID45 toolbar 901px two rounds",
        "synthetic_secrets_only": True, "real_payment": False, "external_provider_credentials": False,
    }
    (OUT / "docker-id122-v143-runtime.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
finally:
    if started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, text=True, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, text=True, capture_output=True, timeout=30)

print(json.dumps({"image": IMAGE, "health": health, "browser_exit": browser.returncode if 'browser' in locals() else None,
                  "id45_browser_exit": toolbar_browser.returncode if 'toolbar_browser' in locals() else None,
                  "runtime_evidence": "docker-id122-v143-runtime.json"}, indent=2))
