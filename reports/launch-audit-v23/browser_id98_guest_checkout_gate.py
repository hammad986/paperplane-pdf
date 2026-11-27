"""Verify guest checkout is gated before any billing request in fresh local runs."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

results: list[dict] = []
failures: list[str] = []
with TemporaryDirectory(prefix="paperplane-id98-guest-checkout-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no, viewport in ((1, {"width": 1366, "height": 900}), (2, {"width": 390, "height": 844})):
                context = browser.new_context(viewport=viewport)
                page = context.new_page()
                errors: list[str] = []
                billing_posts: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: billing_posts.append(request.url)
                        if request.method == "POST" and "/api/billing/checkout-session" in request.url else None)
                page.goto(base + "/", wait_until="networkidle", timeout=20000)
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)
                if viewport["width"] <= 900:
                    page.locator("#mobile-menu-btn").click()
                    page.locator("#sidebar-upgrade-btn").click()
                else:
                    page.locator("#topbar-upgrade-btn").click()
                checkout = page.locator("#student-cashfree-checkout-btn")
                checkout.wait_for(state="visible")
                checkout.click()
                gate = page.locator("[role=dialog], #auth-modal, .auth-modal").filter(
                    has_text="sign in or create an account").first
                gate.wait_for(state="visible", timeout=5000)
                copy = gate.inner_text()
                assert "sign in or create an account" in copy.lower(), copy
                assert not billing_posts, billing_posts
                assert not errors, errors
                overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
                assert not overflow, f"Horizontal overflow at {viewport['width']}px"
                results.append({"round": round_no, "viewport": viewport, "visible": True,
                                "account_required_copy": copy, "billing_posts": billing_posts,
                                "horizontal_overflow": overflow, "page_errors": errors})
                context.close()
            browser.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()

output = ROOT / "reports" / "launch-audit-v23" / "browser-id98-guest-checkout-gate.json"
output.write_text(json.dumps({"results": results, "failures": failures}, indent=2), encoding="utf-8")
print(json.dumps({"rounds": len(results), "failures": failures, "evidence": str(output)}, indent=2))
assert len(results) == 2 and not failures
