"""Check current local guest billing gate in Chromium at desktop and phone widths."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

rounds = []
with TemporaryDirectory(prefix="paperplane-id29-guest-gate-") as temporary:
    app, base, _identity = helper.start_server(Path(temporary) / "data")
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
            for round_number, width in ((1, 1366), (2, 390)):
                context = browser.new_context(viewport={"width": width, "height": 844})
                page = context.new_page()
                errors: list[str] = []
                checkout_posts: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)[:300]))
                page.on("request", lambda request: checkout_posts.append(request.url)
                        if request.method == "POST" and "/api/billing/checkout-session" in request.url else None)
                response = page.goto(base + "/", wait_until="domcontentloaded", timeout=15000)
                assert response and response.status == 200
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=15000)
                if width < 700:
                    page.locator("#mobile-menu-btn").click()
                    page.locator("#sidebar-upgrade-btn").click()
                else:
                    page.locator("#topbar-upgrade-btn").click()
                button = page.locator("#student-cashfree-checkout-btn")
                button.wait_for(state="visible")
                button.click()
                dialog = page.locator("#auth-modal").filter(has_text="sign in or create an account")
                dialog.wait_for(state="visible", timeout=5000)
                copy = dialog.inner_text()
                assert "Please sign in or create an account to subscribe." in copy
                assert not checkout_posts, checkout_posts
                assert not errors, errors
                rounds.append({"round": round_number, "viewport": width, "http_status": response.status,
                               "account_gate_visible": True, "checkout_session_posts": checkout_posts,
                               "page_errors": errors})
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"local_candidate": "current workspace", "rounds": rounds,
          "passes": len(rounds) == 2 and all(row["account_gate_visible"]
                                             and not row["checkout_session_posts"] and not row["page_errors"]
                                             for row in rounds)}
path = OUT / "browser-id29-current-guest-checkout-gate.json"
path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
assert report["passes"]
