"""Inject one transient status-poll 502 and verify the real server job completes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id106-status-retry-") as temp:
    root = Path(temp)
    fixture = root / "id106-status-retry.pdf"
    with fitz.open() as document:
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 72), "ID106 RETRY OUTPUT MARKER")
        document.save(fixture)

    app, base, _ = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"app exited with {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                failed_status_poll = {"value": False}
                status_poll_paths = []

                def intercept_status_poll(route):
                    request = route.request
                    if request.method == "GET" and "/api/jobs/" in request.url and not request.url.endswith("/download"):
                        status_poll_paths.append(request.url)
                        if not failed_status_poll["value"]:
                            failed_status_poll["value"] = True
                            route.fulfill(status=502, content_type="application/json", body='{"detail":"temporary upstream gateway error"}')
                            return
                    route.continue_()

                page.route("**/api/jobs/**", intercept_status_poll)
                response = page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.evaluate("""() => {const toggle=document.querySelector('#client-privacy-toggle');if(toggle.checked){toggle.checked=false;toggle.dispatchEvent(new Event('change',{bubbles:true}));}}""")
                page.wait_for_function("state.clientSideMode===false")
                page.locator("#file-input").set_input_files(str(fixture))
                page.locator("#file-list .file-row-name").wait_for(state="visible", timeout=10000)
                page.locator("#run-button").click()
                page.get_by_text("Retrying status check (1/3)").wait_for(state="visible", timeout=15000)
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#result-download-link").click()
                output = root / f"id106-output-{number}.pdf"
                download_event.value.save_as(output)
                with fitz.open(output) as document:
                    pages = document.page_count
                    text = document[0].get_text().strip()
                    rotation = document[0].rotation
                assert pages == 1 and "ID106 RETRY OUTPUT MARKER" in text and rotation == 90, {"pages": pages, "text": text, "rotation": rotation}
                assert failed_status_poll["value"] and len(status_poll_paths) >= 2, status_poll_paths
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id106-status-retry-round{number}.png"), full_page=True)
                rounds.append({"round": number, "status_poll_http_502_injected": True, "status_poll_attempts": len(status_poll_paths), "output_pages": pages, "output_rotation": rotation, "expected_marker": "ID106 RETRY OUTPUT MARKER", "page_errors": errors})
                context.close()
            browser.close()
        result = {"scenario": "authenticated-free-safe local server job with a single transient 502 on GET status polling", "rounds": rounds}
        (OUT / "browser-id106-transient-job-poll-retry.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
