"""Exercise delayed auth restoration across home, tools, and Settings."""
from __future__ import annotations
import importlib.util, json, socket, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("first_paint_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

def main() -> None:
    evidence = []
    with helpers.TemporaryDirectory(prefix="paperplane-first-paint-") as temp:
        app, base, identities = helpers.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2): break
                except OSError:
                    if app.poll() is not None: raise RuntimeError("Local app exited")
                    time.sleep(0.1)
            else: raise RuntimeError("Local app did not become ready")
            routes = ("/", "/merge-pdf", "/compress-pdf", "/translate-pdf", "/settings")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for round_number in (1, 2):
                    context = browser.new_context()
                    context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1], "url": base, "httpOnly": True}])
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("""(() => {
                      const nativeFetch = window.fetch.bind(window);
                      window.fetch = (resource, options) => {
                        const url = typeof resource === 'string' ? resource : resource?.url || '';
                        if (url.includes('/api/auth/me')) return new Promise((resolve, reject) => setTimeout(() => nativeFetch(resource, options).then(resolve, reject), 1800));
                        return nativeFetch(resource, options);
                      };
                    })();""")
                    for route in routes:
                        page.goto(base + route, wait_until="domcontentloaded")
                        page.wait_for_timeout(120)
                        pending = page.evaluate("document.body.classList.contains('auth-pending')")
                        guest_shell = page.locator("#topbar-auth-guest").is_visible()
                        badge = page.locator("#tool-tier-badge")
                        initial_badge = badge.inner_text() if badge.count() and badge.is_visible() else None
                        assert pending, {"route": route, "pending": pending, "badge": initial_badge}
                        assert not guest_shell, {"route": route, "guest_shell": guest_shell}
                        assert not (initial_badge and "Free Guest" in initial_badge), {"route": route, "badge": initial_badge}
                        page.locator("#topbar-auth-user").wait_for(state="visible", timeout=6000)
                        page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=3000)
                        settled_badge = badge.inner_text() if badge.count() and badge.is_visible() else None
                        if settled_badge:
                            assert "Student" in settled_badge, {"route": route, "settled_badge": settled_badge}
                        evidence.append({"round": round_number, "route": route, "auth_pending_shell_hidden": True,
                                         "initial_tier_badge": initial_badge, "settled_tier_badge": settled_badge,
                                         "paid_auth_visible_after_restore": True})
                    assert not errors, errors
                    context.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-first-paint-paid-auth.json"
    out.write_text(json.dumps({"routes": evidence, "page_errors": []}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"routes": evidence, "page_errors": []}, indent=2))

if __name__ == "__main__": main()
