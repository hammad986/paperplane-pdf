"""Exercise signed guest quota isolation through two independent browser contexts."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id29-quota-browser-") as temporary:
    root = Path(temporary)
    source = root / "quota.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "ID29 guest quota isolation source marker")
        document.save(source)
    pdf_bytes = source.read_bytes()

    app, base, _identity = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app did not start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            contexts = [browser.new_context(viewport={"width": 1366, "height": 900}) for _ in range(2)]
            pages = [context.new_page() for context in contexts]
            errors: list[str] = []
            for page in pages:
                page.on("pageerror", lambda error: errors.append(str(error)[:300]))
                response = page.goto(base + "/", wait_until="domcontentloaded", timeout=15000)
                assert response and response.status == 200
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)

            cookies = [context.cookies(base) for context in contexts]
            quota_cookies = [next((cookie for cookie in jar if cookie["name"] == "paperplane_guest_quota"), None)
                             for jar in cookies]
            assert all(quota_cookies) and quota_cookies[0]["value"] != quota_cookies[1]["value"]

            submitted = []
            for context, count in zip(contexts, (2, 1)):
                jobs = []
                for _ in range(count):
                    response = context.request.post(
                        base + "/api/jobs",
                        multipart={"operation": "merge", "options": "{}",
                                   "files": {"name": "quota.pdf", "mimeType": "application/pdf", "buffer": pdf_bytes}},
                        timeout=15000,
                    )
                    assert response.status == 202, (response.status, response.text())
                    job_id = response.json()["job_id"]
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        status = context.request.get(base + f"/api/jobs/{job_id}", timeout=5000)
                        assert status.status == 200, (status.status, status.text())
                        payload = status.json()
                        if payload.get("status") in {"completed", "failed"}:
                            break
                        time.sleep(0.1)
                    assert payload.get("status") == "completed", payload
                    jobs.append(job_id)
                billing = context.request.get(base + "/api/billing/status", timeout=10000)
                assert billing.status == 200
                usage = billing.json()["usage_today"]
                assert usage == count, {"expected": count, "actual": usage, "billing": billing.json()}
                submitted.append({"jobs_completed": len(jobs), "usage_today": usage})

            assert not errors, errors
            browser.close()
            report = {"guest_quota_cookies_distinct": True, "contexts": submitted,
                      "source_marker": "ID29 guest quota isolation source marker", "page_errors": errors,
                      "result": "PASS"}
    finally:
        app.terminate()
        app.wait(timeout=10)

path = OUT / "browser-id29-current-guest-quota-isolation.json"
path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
