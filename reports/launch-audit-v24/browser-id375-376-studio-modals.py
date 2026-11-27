"""Verify Studio Compress/OCR errors stay visible and retry recovers in Chrome."""
from __future__ import annotations
import json, os, socket, secrets, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def main() -> None:
    evidence = {"page_errors": [], "console_errors": [], "compress": {}, "ocr": {}}
    with TemporaryDirectory(prefix="paperplane-v24-studio-modals-") as temp_name:
        temp = Path(temp_name); data_dir = temp / "data"; data_dir.mkdir()
        fixture = temp / "one-page.pdf"
        doc = fitz.open(); page = doc.new_page(); page.insert_text((72, 72), "Studio modal recovery marker"); doc.save(fixture); doc.close()
        pdf_bytes = fixture.read_bytes()
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0)); port = candidate.getsockname()[1]
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_")) and k not in {"TESTING", "SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV":"1", "PAPERPLANE_ENV":"development", "PAPERPLANE_DATA_DIR":str(data_dir), "PAPERPLANE_PORT":str(port), "PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48), "PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32), "PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48), "PAPERPLANE_SECURE_COOKIES":"false", "PYTHONPATH":str(ROOT)})
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local app did not start")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width":1366,"height":900})
                page.on("pageerror", lambda e:evidence["page_errors"].append(str(e)))
                page.on("console", lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
                compress_calls = 0; ocr_calls = 0
                def route_handler(route):
                    nonlocal compress_calls, ocr_calls
                    path = route.request.url.split(str(port))[-1]
                    if path == "/api/studio/compress/analyze":
                        route.fulfill(status=200, content_type="application/json", body=json.dumps({"analysis":{"page_count":1,"total_images":0,"raster_percentage":0,"opportunity":"Low","estimated_reduction":"0%"}})); return
                    if path == "/api/studio/compress":
                        compress_calls += 1
                        if compress_calls == 1:
                            route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail":"Controlled compression failure"})); return
                        route.fulfill(status=200, content_type="application/pdf", body=pdf_bytes, headers={"X-Original-Size":str(len(pdf_bytes)),"X-Output-Size":str(len(pdf_bytes)),"X-Percent-Saved":"0"}); return
                    if path == "/api/studio/ocr":
                        ocr_calls += 1
                        if ocr_calls == 1:
                            route.fulfill(status=504, content_type="application/json", body=json.dumps({"detail":"Controlled OCR timeout"})); return
                        route.fulfill(status=200, content_type="application/pdf", body=pdf_bytes, headers={"X-Pages-OCRed":"1","X-Extracted-Chars":"30","X-Elapsed-Seconds":"0.1"}); return
                    route.continue_()
                page.route("**/api/studio/**", route_handler)
                response = page.goto(f"http://127.0.0.1:{port}/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("Boolean(window.PaperplaneOptimization)")

                page.evaluate("bytes => window.PaperplaneOptimization.openCompressModal(new File([Uint8Array.from(bytes)], 'modal-source.pdf', {type:'application/pdf'}))", list(pdf_bytes))
                page.wait_for_function("!document.querySelector('#compress-modal').hidden")
                page.locator("#btn-apply-compress").click()
                page.locator("#compress-error-box").wait_for(state="visible", timeout=15000)
                first_error = page.locator("#compress-error-box").inner_text()
                assert "original PDF is still open" in first_error and page.locator("#compress-modal").is_visible()
                assert page.locator("#btn-apply-compress").inner_text() == "Retry Compression →"
                page.locator("#btn-apply-compress").click()
                page.wait_for_function("document.querySelector('#compress-modal').hidden", timeout=20000)
                evidence["compress"] = {"failure_kept_modal_open":True,"error_copy":first_error,"retry_succeeded":compress_calls==2,"output_page_count":page.locator("#studio-page-stack .studio-page-sheet").count()}
                assert evidence["compress"]["retry_succeeded"] and evidence["compress"]["output_page_count"] == 1

                page.evaluate("bytes => window.PaperplaneOptimization.openOcrModal(new File([Uint8Array.from(bytes)], 'modal-source.pdf', {type:'application/pdf'}))", list(pdf_bytes))
                page.wait_for_function("!document.querySelector('#ocr-modal').hidden")
                page.locator("#btn-apply-ocr").click()
                page.wait_for_function("document.querySelector('#ocr-progress-pct')?.textContent === 'Failed'", timeout=15000)
                first_error = page.locator("#ocr-progress-status").inner_text()
                assert "original PDF is unchanged" in first_error and page.locator("#ocr-modal").is_visible()
                assert page.locator("#btn-apply-ocr").inner_text() == "Retry OCR →"
                page.locator("#btn-apply-ocr").click()
                page.wait_for_function("document.querySelector('#ocr-modal').hidden", timeout=20000)
                evidence["ocr"] = {"failure_kept_modal_open":True,"error_copy":first_error,"retry_succeeded":ocr_calls==2,"output_page_count":page.locator("#studio-page-stack .studio-page-sheet").count()}
                assert evidence["ocr"]["retry_succeeded"] and evidence["ocr"]["output_page_count"] == 1
                injected_failures = [message for message in evidence["console_errors"] if "503 (Service Unavailable)" in message or "504 (Gateway Timeout)" in message]
                unexpected_console_errors = [message for message in evidence["console_errors"] if message not in injected_failures]
                assert not evidence["page_errors"] and len(injected_failures) == 2 and not unexpected_console_errors, evidence
                evidence["expected_injected_console_errors"] = injected_failures
                evidence["unexpected_console_errors"] = unexpected_console_errors
                evidence["result"] = "passed"
                (OUT / "browser-id375-376-studio-modals.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence, indent=2))
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=8)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)

if __name__ == "__main__": main()
