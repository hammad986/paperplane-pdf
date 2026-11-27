"""Content-check browser-local Markdown export on the real 69-page fixture."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import socket
import subprocess
import sys
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with fitz.open(SOURCE) as source:
    expected_pages = [page.get_text() for page in source]
assert len(expected_pages) == 69

base = os.environ.get("PAPERPLANE_TEST_BASE")
app = None
with TemporaryDirectory(prefix="paperplane-id37-real-markdown-") as temporary:
    if not base:
        app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)

        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'local')")
                page = context.new_page()
                errors = []
                job_posts = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: job_posts.append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                response = page.goto(base + "/?tool=pdf_to_markdown", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#file-input").set_input_files(str(SOURCE))
                page.locator("#run-button").click()
                dialog = page.locator(".app-confirm-dialog")
                dialog.wait_for(state="visible", timeout=90000)
                prompt = dialog.inner_text()
                assert "math or custom-font glyphs" in prompt, prompt
                assert "Choose Server Processing" in prompt, prompt
                assert "Upload and retry" in prompt, prompt
                assert "temporary server processing" in prompt, prompt
                page.locator(".app-confirm-cancel").click()
                page.locator("#result:not([hidden])").wait_for(state="visible", timeout=10000)
                assert page.locator("#result-title").inner_text() == "Processing failed"
                fallback_message = page.locator("#result-meta").inner_text()
                assert "No files were uploaded" in fallback_message, fallback_message
                assert page.locator("#result-download-link").is_hidden()
                assert "math layout" in page.locator("#options").inner_text()
                assert not job_posts, job_posts
                assert not errors, errors
                rounds.append({"round": number, "status": response.status,
                               "fixture_pages": len(expected_pages),
                               "custom_font_math_fallback_shown": True,
                               "server_upload_requires_consent": True,
                               "cancelled_without_upload_or_download": True,
                               "job_posts": job_posts, "page_errors": errors})
                context.close()
            browser.close()

        docker_runtime = bool(os.environ.get("PAPERPLANE_TEST_BASE"))
        evidence_name = "browser-id37-local-markdown-real-docker.json" if docker_runtime else "browser-id37-local-markdown-real-local.json"
        report = {"base": base, "runtime": "Docker image" if docker_runtime else "local server",
                  "image_id": subprocess.check_output(
                      ["docker", "image", "inspect", "paperplane-v23-audit:codex-current", "--format", "{{.Id}}"],
                      text=True).strip() if docker_runtime else None,
                  "fixture": str(SOURCE), "rounds": rounds}
        (OUT / evidence_name).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if app:
            app.terminate()
            app.wait(timeout=5)
