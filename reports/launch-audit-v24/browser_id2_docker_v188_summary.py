"""Check the 69-page offline Executive Brief in the rebuilt production image."""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import socket
import subprocess
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id2-docker-v188-summary.json"
IMAGE = "pdf_splitter-paperplane:latest"
CONTAINER = "paperplane-v24-id2-v188-summary"
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 18589))

fixture = OUT.with_name("id2-docker-v188-69page.pdf")
with fitz.open() as pdf:
    for number in range(1, 70):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Quarterly Operations Review — Page {number}")
        page.insert_text((72, 112), f"Unique verified fact for source page {number}: completion rate is {number} percent.")
        if number == 69:
            page.insert_text((72, 152), "Final page decision: retain all 69 page records for final audit.")
    pdf.save(fixture)

env_values = {
    "PAPERPLANE_ENV": "production",
    "PAPERPLANE_SKIP_DOTENV": "1",
    "PAPERPLANE_WORKERS": "4",
    "PAPERPLANE_DATA_DIR": "/data",
    "PAPERPLANE_PORT": "8501",
    "PAPERPLANE_PUBLIC_URL": "https://paperplane.example.test",
    "PAPERPLANE_SECURE_COOKIES": "false",
    "PAPERPLANE_JOB_TTL_SECONDS": "86400",
    "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
    "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
    "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
    "ADMIN_ALERT_EMAIL": "audit@example.invalid",
    "CASHFREE_ENV": "TEST",
}
container_started = False
errors: list[str] = []
try:
    subprocess.run([
        "docker", "run", "-d", "--name", CONTAINER, "--restart=no", "--cpus=4", "--memory=4g",
        "--pids-limit=1024", "--security-opt=no-new-privileges", "-p", "127.0.0.1:18589:8501",
        "--tmpfs", "/data:rw,nosuid,nodev,size=512m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
        *[arg for key, value in env_values.items() for arg in ("-e", f"{key}={value}")], IMAGE,
    ], check=True, capture_output=True, text=True)
    container_started = True
    for _ in range(90):
        try:
            health = json.loads(subprocess.check_output([
                "docker", "exec", CONTAINER, "python", "-c",
                "import urllib.request,json;print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8501/api/health',timeout=3))))",
            ], text=True, stderr=subprocess.DEVNULL))
            if health.get("status") == "ok":
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("The v188 image did not become healthy")

    evidence: dict[str, object] = {"health": health, "page_errors": [], "console_errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.route("**/api/ai/capabilities", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"executive_brief_available": True, "reason": None}),
        ))
        response = page.goto("http://127.0.0.1:18589/ai-intelligence", wait_until="domcontentloaded")
        assert response and response.status == 200
        page.locator("#ai-file-input").set_input_files(str(fixture))
        page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=30_000)
        page.wait_for_function("document.querySelector('#trigger-summary-btn') && !document.querySelector('#trigger-summary-btn').disabled", timeout=30_000)
        with page.expect_response(lambda item: "/api/ai/summarize" in item.url, timeout=300_000) as response_event:
            page.locator("#trigger-summary-btn").click()
        summary_response = response_event.value
        payload = summary_response.json()
        page.wait_for_function("document.querySelector('#summary-mode-badge')?.innerText.includes('Offline')", timeout=30_000)
        summary = str(payload.get("summary", ""))
        citations = payload.get("citations", [])
        missing_summary_facts = [n for n in range(1, 70) if f"completion rate is {n} percent" not in summary]
        with page.expect_download(timeout=30_000) as download_event:
            page.locator("#download-summary-pdf-btn").click()
        download = download_event.value
        output = OUT.with_name("id2-docker-v188-summary.pdf")
        download.save_as(str(output))
        with fitz.open(output) as pdf:
            pdf_text = "\n".join(item.get_text() for item in pdf)
            missing_output_facts = [n for n in range(1, 70) if f"completion rate is {n} percent" not in pdf_text]
            download_check = {
                "filename": download.suggested_filename,
                "pages": pdf.page_count,
                "pdf_signature": output.read_bytes()[:5].decode("ascii"),
                "all_69_page_facts": not missing_output_facts,
                "missing_page_facts": missing_output_facts,
                "final_decision": "retain all 69 page records" in pdf_text,
            }
        evidence.update({
            "http_status": summary_response.status,
            "summary_mode": payload.get("summary_mode"),
            "citation_count": len(citations),
            "all_pages_cited": set(citations) == set(range(1, 70)),
            "summary_has_all_69_facts": not missing_summary_facts,
            "summary_missing_facts": missing_summary_facts,
            "offline_disclosure": "Offline Analysis" in summary,
            "download": download_check,
            "page_errors": errors,
            "console_errors": [],
        })
        browser.close()

    evidence["passed"] = bool(
        evidence["http_status"] == 200
        and evidence["summary_mode"] == "offline_extractive"
        and evidence["all_pages_cited"]
        and evidence["summary_has_all_69_facts"]
        and evidence["offline_disclosure"]
        and download_check["pdf_signature"] == "%PDF-"
        and download_check["all_69_page_facts"]
        and download_check["final_decision"]
        and not errors
    )
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=True))
    if not evidence["passed"]:
        raise SystemExit(1)
finally:
    if container_started:
        subprocess.run(["docker", "stop", "--time", "10", CONTAINER], check=False, capture_output=True, timeout=30)
        subprocess.run(["docker", "rm", "--force", CONTAINER], check=False, capture_output=True, timeout=30)
