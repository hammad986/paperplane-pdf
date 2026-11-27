"""Run concurrent Watermark submissions/downloads in disposable production Docker.

The test is intentionally isolated, synthetic, and billing-free. It verifies the
browser -> HTTP job queue -> worker -> content-checked PDF path under concurrency.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from urllib.request import urlopen

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGE = os.environ.get("PAPERPLANE_TEST_IMAGE_TAG", "paperplane-v23-audit:codex-current")
EXPECTED_IMAGE_ID = os.environ.get("PAPERPLANE_TEST_IMAGE_ID", "sha256:b3a5c5c0da22de2de0eec8a65824ef8c18be68550a4a3707e65525fc55c91d47")
CONTAINER = os.environ.get("PAPERPLANE_TEST_CONTAINER", "paperplane-v23-id28-concurrency")
BASE = os.environ.get("PAPERPLANE_TEST_BASE", "http://127.0.0.1:18503")
ROUNDS = 4
CONCURRENCY = 4
PAGE_COUNT = 2
EVIDENCE = OUT / os.environ.get("PAPERPLANE_TEST_EVIDENCE", "browser-id28-concurrent-watermark.json")


def run(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


def main() -> int:
    image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]).stdout.strip()
    if image_id != EXPECTED_IMAGE_ID:
        raise RuntimeError(f"Refusing unexpected image digest: {image_id}")
    existing = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name=^{CONTAINER}$"],
        check=True, text=True, capture_output=True,
    ).stdout.strip()
    if existing:
        raise RuntimeError(f"Refusing to replace existing container {CONTAINER}")

    admin_key = secrets.token_urlsafe(48)
    admin_code = secrets.token_urlsafe(24)
    session_secret = secrets.token_urlsafe(48)
    args = [
        "docker", "run", "-d", "--name", CONTAINER,
        "--restart=no", "--cpus=4", "--memory=4g", "--pids-limit=128",
        "--security-opt=no-new-privileges", "-p", "127.0.0.1:18503:8501",
        "--tmpfs", "/data:rw,nosuid,nodev,size=512m",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
        "-e", "PAPERPLANE_ENV=production", "-e", "PAPERPLANE_SKIP_DOTENV=1",
        "-e", "PAPERPLANE_WORKERS=4", "-e", "PAPERPLANE_DATA_DIR=/data",
        "-e", "PAPERPLANE_PORT=8501", "-e", "PAPERPLANE_PUBLIC_URL=https://paperplane.example.test",
        "-e", "PAPERPLANE_SECURE_COOKIES=false", "-e", f"PAPERPLANE_ADMIN_KEY={admin_key}",
        "-e", f"PAPERPLANE_ADMIN_CODE={admin_code}", "-e", f"PAPERPLANE_SESSION_SECRET={session_secret}",
        "-e", "ADMIN_ALERT_EMAIL=audit@example.invalid", "-e", "CASHFREE_ENV=TEST", IMAGE,
    ]
    started = False
    page_errors: list[str] = []
    rounds: list[dict[str, object]] = []
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
            raise RuntimeError("Disposable Docker runtime did not become healthy")

        with tempfile.TemporaryDirectory(prefix="paperplane-id28-browser-concurrency-") as temp:
            source = Path(temp) / "watermark-source.pdf"
            doc = fitz.open()
            for index in range(1, PAGE_COUNT + 1):
                page = doc.new_page()
                page.insert_text((72, 72), f"ID28-HTTP-PAGE-{index}", fontsize=14)
            doc.save(source)
            doc.close()
            source_b64 = base64.b64encode(source.read_bytes()).decode("ascii")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 850})
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(BASE, wait_until="domcontentloaded")
                email = "audit-id28-concurrency@example.invalid"
                password = "Dummy-Password-Only-ID28!"
                seed_code = (
                    "from persistence import create_user,get_user_by_email,set_user_tier; "
                    f"row=get_user_by_email('{email}'); uid=row['id'] if row else create_user('{email}','{password}'); "
                    "set_user_tier(uid,'pro'); print('seeded')"
                )
                seeded = subprocess.run(
                    ["docker", "exec", CONTAINER, "python", "-c", seed_code],
                    text=True, capture_output=True, timeout=30,
                )
                if seeded.returncode or "seeded" not in seeded.stdout:
                    raise RuntimeError("Could not create disposable synthetic account")
                login = page.request.post(
                    BASE + "/api/auth/login", data={"email": email, "password": password},
                    headers={"content-type": "application/json"},
                )
                if login.status != 200:
                    raise RuntimeError(f"Synthetic login failed with {login.status}")

                for round_number in range(1, ROUNDS + 1):
                    started_at = time.perf_counter()
                    jobs = page.evaluate(
                        """async cfg => {
                          const payloads = Array.from({length: cfg.count}, (_, i) => ({
                            id: `${cfg.round}-${i + 1}`, text: `ID28-HTTP-WATERMARK-${cfg.round}-${i + 1}`
                          }));
                          const submitted = await Promise.all(payloads.map(async item => {
                            const form = new FormData();
                            form.append('operation', 'watermark');
                            form.append('options', JSON.stringify({text: item.text, opacity: 0.2}));
                            const raw = atob(cfg.pdf); const bytes = new Uint8Array(raw.length);
                            for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                            form.append('files', new File([bytes], `id28-${item.id}.pdf`, {type:'application/pdf'}));
                            const response = await fetch('/api/jobs', {method:'POST', body:form});
                            const body = await response.json().catch(() => ({}));
                            if (!response.ok) throw new Error(`submit ${item.id}: ${response.status} ${JSON.stringify(body)}`);
                            return {...item, job:body};
                          }));
                          return await Promise.all(submitted.map(async item => {
                            let state = null;
                            for (let attempt = 0; attempt < 240; attempt++) {
                              await new Promise(resolve => setTimeout(resolve, 250));
                              const response = await fetch(item.job.status_url);
                              if (!response.ok) throw new Error(`status ${item.id}: ${response.status}`);
                              state = await response.json();
                              if (state.status === 'completed') break;
                              if (state.status === 'failed') throw new Error(`failed ${item.id}: ${state.error}`);
                            }
                            if (state?.status !== 'completed') throw new Error(`timeout ${item.id}`);
                            const response = await fetch(item.job.download_url);
                            if (!response.ok) throw new Error(`download ${item.id}: ${response.status}`);
                            const data = new Uint8Array(await response.arrayBuffer());
                            let binary = '';
                            for (let i = 0; i < data.length; i += 8192) binary += String.fromCharCode(...data.subarray(i, i + 8192));
                            return {id:item.id, text:item.text, bytes:btoa(binary), output_name:state.output_name, status:state.status};
                          }));
                        }""",
                        {"count": CONCURRENCY, "round": round_number, "pdf": source_b64},
                    )
                    checked = []
                    for item in jobs:
                        data = base64.b64decode(item["bytes"])
                        pdf = fitz.open(stream=data, filetype="pdf")
                        text = "\n".join(p.get_text() for p in pdf)
                        checked.append({
                            "id": item["id"], "http_job_status": item["status"],
                            "valid_pdf": data.startswith(b"%PDF-"),
                            "pages": pdf.page_count,
                            "source_markers_preserved": all(f"ID28-HTTP-PAGE-{i}" in text for i in range(1, PAGE_COUNT + 1)),
                            "unique_watermark_present": item["text"] in text,
                            "output_bytes": len(data),
                        })
                        pdf.close()
                    rounds.append({
                        "round": round_number, "concurrency": CONCURRENCY,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
                        "outputs": checked,
                    })
                browser.close()

        evidence = {
            "item": 28,
            "image_id": image_id,
            "rounds": ROUNDS,
            "concurrency_per_round": CONCURRENCY,
            "jobs_total": ROUNDS * CONCURRENCY,
            "all_outputs_valid_pdf": all(x["valid_pdf"] for r in rounds for x in r["outputs"]),
            "all_page_markers_preserved": all(x["source_markers_preserved"] for r in rounds for x in r["outputs"]),
            "all_unique_watermarks_preserved": all(x["unique_watermark_present"] for r in rounds for x in r["outputs"]),
            "all_jobs_completed": all(x["http_job_status"] == "completed" for r in rounds for x in r["outputs"]),
            "page_errors": page_errors,
            "runtime_health": health,
            "round_results": rounds,
            "payment_attempted": False,
            "provider_credentials": False,
            "storage": "disposable tmpfs only",
            "limitation": "A bounded concurrency run does not disprove the previously observed intermittent queued-job stall.",
        }
        EVIDENCE.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
        success = all(evidence[k] for k in (
            "all_outputs_valid_pdf", "all_page_markers_preserved", "all_unique_watermarks_preserved",
            "all_jobs_completed",
        )) and not page_errors
        return 0 if success else 1
    finally:
        if started:
            subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, capture_output=True, timeout=30)
            subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, capture_output=True, timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
