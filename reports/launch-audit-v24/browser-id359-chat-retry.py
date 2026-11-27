"""Exercise AI Chat retry and duplicate-question handling in local Chrome."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

with TemporaryDirectory(prefix="paperplane-id359-chat-") as temp:
    app, base, _identity = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError("local app did not start")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            errors = []
            requests = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.route("**/api/ai/chat/stream", lambda route: None)

            def controlled_response(route):
                requests.append(route.request.post_data or "")
                if len(requests) == 1:
                    body = 'event: error\ndata: {"message":"AI service returned HTTP 429. Please retry later."}\n\n'
                else:
                    body = ('event: replace\ndata: {"text":"Fallback answer for the question."}\n\n'
                            'event: done\ndata: {"citations":[],"mode":"provider_fallback"}\n\n')
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.unroute("**/api/ai/chat/stream")
            page.route("**/api/ai/chat/stream", controlled_response)
            response = page.goto(base + "/ai-intelligence", wait_until="domcontentloaded", timeout=20000)
            page.locator("#chat-input").wait_for(state="visible", timeout=15000)
            question = "Explain why the sky looks blue."
            page.locator("#chat-input").fill(question)
            page.locator("#chat-send-btn").click()
            page.locator(".ai-chat-retry").wait_for(state="visible", timeout=15000)
            failed_user_count = page.locator(".chat-bubble.user").count()
            assert failed_user_count == 1, failed_user_count
            page.locator(".ai-chat-retry").click()
            page.get_by_text("Fallback answer for the question.", exact=False).wait_for(timeout=15000)
            page.wait_for_function("document.querySelectorAll('.chat-bubble.user').length === 1")
            assert len(requests) == 2, len(requests)
            assert question in page.locator("#chat-messages").inner_text()
            assert page.get_by_text("Connection interrupted", exact=True).count() == 0
            assert response and response.status == 200 and not errors, {"status": response.status if response else None, "errors": errors}
            evidence = {"result": "passed", "route_status": response.status, "requests": len(requests), "failed_state_user_question_count": failed_user_count, "after_retry_user_question_count": page.locator(".chat-bubble.user").count(), "fallback_answer_visible": True, "retry_error_removed": True, "page_or_console_errors": errors}
            (OUT / "browser-id359-chat-retry.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            browser.close()
    finally:
        app.terminate()
        try: app.wait(timeout=8)
        except Exception: app.kill()
