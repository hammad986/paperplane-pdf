"""Exercise Studio compression and OCR modal retries in local Chrome."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main() -> None:
    evidence: dict = {"cases": {}, "page_errors": [], "console_errors": [], "controlled_failure_console_messages": []}
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Studio retry verification original document", fontsize=15)
    pdf_bytes = doc.tobytes()
    doc.close()
    encoded_pdf = base64.b64encode(pdf_bytes).decode("ascii")

    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="paperplane-v24-retry-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "data"
        data_dir.mkdir()
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith((
            "PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
            "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_",
        )) and key not in {"TESTING", "SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development",
                    "PAPERPLANE_DATA_DIR": str(data_dir), "PAPERPLANE_PORT": str(port),
                    "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
                    "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
                    "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
                    "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT)})
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                def capture_console(msg):
                    if msg.type != "error":
                        return
                    if "responded with a status of 503" in msg.text:
                        evidence["controlled_failure_console_messages"].append(msg.text)
                    else:
                        evidence["console_errors"].append(msg.text)
                page.on("console", capture_console)
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.evaluate("""b64 => { window.retryFixture = new File(
                  [Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'retry-fixture.pdf',
                  {type:'application/pdf'}); }""", encoded_pdf)

                compress_calls = 0
                compression_requests = 0
                compress_urls = []
                def compress_route(route):
                    nonlocal compress_calls, compression_requests
                    compress_calls += 1
                    compress_urls.append(route.request.url)
                    if route.request.url.endswith("/analyze"):
                        route.fulfill(status=200, content_type="application/json", body=json.dumps({"analysis": {
                            "page_count": 1, "total_images": 0, "raster_percentage": 0,
                            "opportunity": "No large image streams", "estimated_reduction": "0%"}}))
                    else:
                        compression_requests += 1
                        if compression_requests == 1:
                            route.fulfill(status=503, content_type="application/json", body='{"detail":"controlled temporary failure"}')
                            return
                        route.fulfill(status=200, content_type="application/pdf", body=pdf_bytes,
                                      headers={"X-Original-Size": str(len(pdf_bytes)),
                                               "X-Output-Size": str(len(pdf_bytes) - 10),
                                               "X-Percent-Saved": "1"})
                page.route("**/api/studio/compress**", compress_route)
                page.evaluate("async () => await window.PaperplaneOptimization.openCompressModal(window.retryFixture)")
                page.locator("#btn-apply-compress").click()
                try:
                    page.locator("#compress-error-box").wait_for(state="visible", timeout=10000)
                except Exception:
                    raise AssertionError({"calls": compress_calls, "urls": compress_urls,
                        "button": page.locator("#btn-apply-compress").inner_text(),
                        "errors": evidence["page_errors"], "console": evidence["console_errors"]})
                assert page.locator("#compress-modal").is_visible()
                assert "controlled temporary failure" in page.locator("#compress-error-box").inner_text()
                assert page.locator("#btn-apply-compress").inner_text() == "Retry Compression →"
                assert not page.locator("#btn-apply-compress").is_disabled()
                page.locator("#btn-apply-compress").click()
                page.wait_for_function("document.querySelector('#compress-modal').hidden")
                assert compress_calls == 3 and compression_requests == 2, (compress_calls, compression_requests)
                evidence["cases"]["compress"] = {"requests_including_analysis": compress_calls,
                    "failure_visible": True, "retry_succeeded": True, "modal_closed_on_success": True}

                ocr_calls = 0
                def ocr_route(route):
                    nonlocal ocr_calls
                    ocr_calls += 1
                    if ocr_calls == 1:
                        route.fulfill(status=503, content_type="application/json", body='{"detail":"controlled OCR outage"}')
                    else:
                        route.fulfill(status=200, content_type="application/pdf", body=pdf_bytes,
                                      headers={"X-Pages-OCRed": "1", "X-Extracted-Chars": "42", "X-Elapsed-Seconds": "0.1"})
                page.route("**/api/studio/ocr", ocr_route)
                page.evaluate("() => window.PaperplaneOptimization.openOcrModal(window.retryFixture)")
                page.locator("#btn-apply-ocr").click()
                page.get_by_text("OCR failed: controlled OCR outage", exact=False).wait_for()
                assert page.locator("#ocr-modal").is_visible()
                assert page.locator("#ocr-progress-pct").inner_text() == "Failed"
                assert page.locator("#btn-apply-ocr").inner_text() == "Retry OCR →"
                assert not page.locator("#btn-apply-ocr").is_disabled()
                page.locator("#btn-apply-ocr").click()
                page.wait_for_function("document.querySelector('#ocr-modal').hidden")
                assert ocr_calls == 2, ocr_calls
                evidence["cases"]["ocr"] = {"requests": ocr_calls, "failure_visible": True,
                    "failed_progress_not_reset": True, "retry_succeeded": True, "modal_closed_on_success": True}
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                assert len(evidence["controlled_failure_console_messages"]) == 2, evidence
                evidence["result"] = "passed"
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    (OUT / "browser-studio-compress-ocr-retry.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
