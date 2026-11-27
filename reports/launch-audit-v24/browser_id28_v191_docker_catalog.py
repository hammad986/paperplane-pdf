"""Two-round, content-checked browser catalog against the production Docker image."""
from __future__ import annotations
import base64
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
AUDIT_SUFFIX = os.environ.get("PAPERPLANE_AUDIT_SUFFIX", "")
RUN_DIR = OUT / f"docker-catalog-fixtures-current-v191-20261123{AUDIT_SUFFIX}"
EVIDENCE_PATH = OUT / f"browser-id28-v191-style70-current-image-catalog{AUDIT_SUFFIX}.json"
BASE = os.environ.get("PAPERPLANE_AUDIT_BASE", "http://127.0.0.1:18518")
CONTAINER = os.environ.get("PAPERPLANE_AUDIT_CONTAINER", "paperplane-v24-v191-style70-final")
EMAIL = "audit-catalog-v191@example.invalid"
PASSWORD = "Dummy-Password-Only-v191!"
sys.path.insert(0, str(ROOT))
os.environ.update(
    PAPERPLANE_SKIP_DOTENV="1",
    PAPERPLANE_ENV="development",
    PAPERPLANE_DATA_DIR=os.environ.get("PAPERPLANE_AUDIT_DATA_DIR", str(OUT / "runtime-id28-catalog")),
)

def load(name: str, location: Path):
    spec = importlib.util.spec_from_file_location(name, location)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

checks_module = load("v21checks", ROOT / "reports" / "launch-audit-v21" / "tool_content_audit.py")
helper = load("v14helper", ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py")
checks = checks_module.load_previous_checks()
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for _ in range(30):
        try:
            health = page.request.get(BASE + "/api/health", timeout=3000)
            if health.status == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("production-image container did not become healthy")
    seed = "from persistence import create_user,get_user_by_email,set_user_tier; row=get_user_by_email('audit-catalog-v191@example.invalid'); uid=row['id'] if row else create_user('audit-catalog-v191@example.invalid','Dummy-Password-Only-v191!'); set_user_tier(uid,'pro'); print('seeded')"
    seeded = subprocess.run(["docker", "exec", CONTAINER, "python", "-c", seed], capture_output=True, text=True, timeout=30)
    assert seeded.returncode == 0 and "seeded" in seeded.stdout, seeded.stderr
    login = page.request.post(BASE + "/api/auth/login", data={"email": EMAIL, "password": PASSWORD}, headers={"content-type": "application/json"})
    assert login.status == 200, login.text()
    assert page.request.get(BASE + "/api/auth/me").json().get("email") == EMAIL
    home = page.goto(BASE + "/", wait_until="domcontentloaded")
    assert home and home.status == 200
    health_payload = health.json()

    class RemoteServer:
        last_request_at = 0.0

        def get_operations(self):
            response = page.request.get(BASE + "/api/operations")
            assert response.status == 200
            return response.json()

        def process(self, operation, paths, options, output_dir):
            time.sleep(max(0.0, 3.2 - (time.monotonic() - self.last_request_at)))
            self.last_request_at = time.monotonic()
            result = page.evaluate("""async c => {
              const form = new FormData();
              form.append('operation', c.op);
              form.append('options', JSON.stringify(c.options));
              for (const f of c.files) {
                const raw = atob(f.data); const bytes = new Uint8Array(raw.length);
                for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                form.append('files', new File([bytes], f.name));
              }
              let response = await fetch('/api/jobs', {method: 'POST', body: form});
              const body = await response.json().catch(() => ({}));
              if (!response.ok) throw new Error(`job submit ${response.status}: ${JSON.stringify(body)}`);
              let job = body, state;
              for (let i = 0; i < 1200; i++) {
                await new Promise(resolve => setTimeout(resolve, 250));
                response = await fetch(job.status_url);
                if (!response.ok) throw new Error(`status ${response.status}`);
                state = await response.json();
                if (state.status === 'completed') break;
                if (state.status === 'failed') throw new Error(state.error || 'job failed');
              }
              if (state?.status !== 'completed') throw new Error('job timeout');
              response = await fetch(job.download_url);
              if (!response.ok) throw new Error(`download ${response.status}`);
              const bytes = new Uint8Array(await response.arrayBuffer());
              let binary = '';
              for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
              return {name: state.output_name, data: btoa(binary)};
            }""", {
                "op": operation,
                "options": options,
                "files": [{"name": path.name, "data": base64.b64encode(path.read_bytes()).decode("ascii")} for path in paths],
            })
            target = Path(output_dir) / Path(result["name"]).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(result["data"]))
            print(f"round operation completed: {operation}", flush=True)
            return target

    records = []
    for round_number in (1, 2):
        record = checks_module.round_result(round_number, RemoteServer(), checks, RUN_DIR)
        records.append(record)
        counts = {}
        for result in record["results"]:
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(json.dumps({"round": round_number, "counts": counts}), flush=True)
        expected = {"completed": 41, "unavailable": 2, "ssrf_blocked": 1}
        if len(record["results"]) != 44 or counts != expected:
            print(json.dumps({"round": round_number, "failed_operations": [item for item in record["results"] if item["status"] == "failed"]}, indent=2), flush=True)
            raise AssertionError(f"Current-image catalog content checks failed in round {round_number}: {counts}")
    browser.close()
assert not errors, errors
report = {"runtime": "isolated production image; four workers; dummy local account; no AI provider or real payment", "base": BASE, "health": health_payload, "rounds": records, "page_errors": errors}
EVIDENCE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"health": report["health"], "round_statuses": [{s: sum(1 for x in r["results"] if x["status"] == s) for s in sorted({x["status"] for x in r["results"]})} for r in records], "page_errors": errors}, indent=2))


