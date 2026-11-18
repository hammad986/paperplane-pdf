"""Run the exact synthetic production probe PDF through current local offline-summary code."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "live-id2-synthetic-69-pages.pdf"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id2-local-exact-") as temp:
    app, base, identity = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"local app exited during startup with code {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise RuntimeError("local app did not become ready")
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            context.add_cookies([{"name": "paperplane_token", "value": identity["accounts"][0][1], "url": base, "httpOnly": True}])
            context.route("**/api/ai/capabilities", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"executive_brief_available": True, "reason": None})))
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.locator("#ai-file-input").set_input_files(str(FIXTURE))
            page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=20000)
            with page.expect_response(lambda item: "/api/ai/summarize" in item.url, timeout=60000) as response_info:
                page.locator("#trigger-summary-btn").click()
            api_response = response_info.value
            body = api_response.json()
            page.wait_for_function("() => document.querySelector('#summary-display')?.innerText.trim().length > 0", timeout=20000)
            summary = str(body.get("summary") or "")
            visible = page.locator("#summary-display").inner_text()
            all_text = summary + "\n" + visible
            result = {
                "http_status": api_response.status,
                "summary_mode": body.get("summary_mode"),
                "summary_keys": sorted(body.keys()),
                "page24_cancellation": "cancel the duplicate vendor work" in all_text.lower(),
                "page24_spend_limit": "900000" in all_text.replace(",", ""),
                "page69_deadline": "15 december 2026" in all_text.lower(),
                "citations_count": len(body.get("citations", [])),
                "citation_range": [min(body["citations"]), max(body["citations"])] if body.get("citations") else None,
                "page_errors": errors,
            }
            assert result["http_status"] == 200 and result["summary_mode"] == "offline_extractive", result
            assert result["page24_cancellation"] and result["page24_spend_limit"] and result["page69_deadline"], result
            assert result["citation_range"] == [1, 69] and not errors, result
            rounds.append(result)
            context.close()
            browser.close()
        output = {"fixture": FIXTURE.name, "current_local_runtime": True, "rounds": rounds}
        (OUT / "browser-id2-local-exact-fixture-fallback.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            import subprocess
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
