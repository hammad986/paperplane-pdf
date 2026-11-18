"""Verify the sidebar profile shell stays stable while a signed-in paid user resolves."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import sqlite3
import sys
import time
import subprocess

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

ROUTES = ["/apps", "/download", "/privacy", "/terms", "/faq"]


with TemporaryDirectory(prefix="paperplane-id140-pro-") as temp:
    data_dir = Path(temp) / "data"
    app, base, identities = helper.start_server(data_dir)
    try:
        port = int(base.rsplit(":", 1)[1])
        ready = False
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"local app exited during startup with code {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    ready = True
                    break
            except OSError:
                time.sleep(0.15)
        assert ready, "local Paperplane server did not become ready"
        email, token = identities["accounts"][0]
        connection = sqlite3.connect(data_dir / "paperplane.sqlite3")
        try:
            connection.execute(
                "UPDATE users SET tier='student_pro', subscription_status='active' WHERE email=?",
                (email,),
            )
            connection.commit()
        finally:
            connection.close()

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                route_results = []
                page.add_init_script("""
                    (() => {
                      const nativeFetch = window.fetch.bind(window);
                      window.fetch = (input, ...args) => {
                        let path = '';
                        try { path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname; } catch {}
                        if (path === '/api/auth/me') {
                          return new Promise(resolve => setTimeout(() => resolve(nativeFetch(input, ...args)), 1500));
                        }
                        return nativeFetch(input, ...args);
                      };
                    })();
                """)
                for route in ROUTES:
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    assert response and response.status == 200, (route, response.status if response else None)
                    card = page.locator("#sidebar-profile-card")
                    first_paint = page.wait_for_function(
                        "() => { const c=document.querySelector('#sidebar-profile-card'); return c && c.getClientRects().length > 0; }",
                        timeout=4000,
                    )
                    pending = page.locator("body").evaluate("e => e.classList.contains('auth-pending')")
                    first_name = page.locator("#user-name").inner_text().strip()
                    page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                    page.wait_for_function(
                        "() => { const n=document.querySelector('#user-name'); return n && n.textContent.trim() && n.textContent.trim() !== 'Guest Explorer'; }",
                        timeout=10000,
                    )
                    me = page.evaluate("fetch('/api/auth/me',{cache:'no-store'}).then(r=>r.json())")
                    settled_name = page.locator("#user-name").inner_text().strip()
                    assert me.get("authenticated") is True, (route, me)
                    assert me.get("tier") == "student_pro", (route, me)
                    assert pending and first_name != settled_name, (route, pending, first_name, settled_name)
                    assert card.is_visible(), route
                    route_results.append({
                        "route": route,
                        "status": response.status,
                        "first_paint_card_visible": bool(first_paint),
                        "auth_pending_at_first_paint": pending,
                        "unresolved_identity": first_name,
                        "settled_name": settled_name,
                        "authenticated_tier": me.get("tier"),
                    })
                assert not page_errors, page_errors
                rounds.append({"round": round_no, "routes": route_results, "page_errors": page_errors})
                context.close()
            browser.close()

        output = {"account": "disposable signed-in student_pro test account", "rounds": rounds}
        (OUT / "browser-id140-sidebar-profile-pro.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2))
    finally:
        if sys.platform == "win32" and app.poll() is None:
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
