"""Check auth-pending and hydrated UI state across every tool route on v205."""
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v24"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main():
    from server import OPERATION_SLUGS

    routes = sorted(set(["/"] + [f"/{slug}" for slug in OPERATION_SLUGS.values()] + [
        "/settings", "/studio", "/ai-intelligence", "/download", "/pricing", "/developers", "/faq"
    ]))
    with TemporaryDirectory(prefix="paperplane-id168-v205-") as temporary:
        app, base, identities = helper.start_server(Path(temporary) / "server-data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            payload = {"routes": routes, "authenticated": [], "signed_out": [], "page_errors": [], "console_errors": []}
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 390, "height": 844})
                context.add_cookies([{
                    "name": "paperplane_token", "value": identities["accounts"][0][1],
                    "url": base, "httpOnly": True, "secure": False, "sameSite": "Lax",
                }])
                page = context.new_page()
                page.on("pageerror", lambda error: payload["page_errors"].append(str(error)))
                page.on("console", lambda message: payload["console_errors"].append(message.text)
                        if message.type == "error" and "status of 401 (Unauthorized)" not in message.text else None)
                context.add_init_script("""(() => {
                  const nativeFetch = window.fetch.bind(window);
                  window.__paperplaneAuthDelayUsed = false;
                  window.fetch = (input, init) => {
                    const url = typeof input === 'string' ? input : input?.url || '';
                    if (url.includes('/api/auth/me') && !window.__paperplaneAuthDelayUsed) {
                      window.__paperplaneAuthDelayUsed = true;
                      return new Promise(resolve => setTimeout(() => resolve(nativeFetch(input, init)), 2500));
                    }
                    return nativeFetch(input, init);
                  };
                })();""")
                for path in routes:
                    response = page.goto(base + path, wait_until="domcontentloaded", timeout=20000)
                    if not response or response.status != 200:
                        raise AssertionError({"route": path, "status": response.status if response else None})
                    initial = page.evaluate("""() => ({
                      pending: document.body.classList.contains('auth-pending'),
                      guestVisibility: getComputedStyle(document.querySelector('#topbar-auth-guest')).visibility,
                      userVisibility: getComputedStyle(document.querySelector('#topbar-auth-user')).visibility,
                      profileVisibility: getComputedStyle(document.querySelector('#user-name')).visibility
                    })""")
                    page.wait_for_function("window.state?.user?.email && !document.body.classList.contains('auth-pending')", timeout=12000)
                    final = page.evaluate("""() => ({
                      email: state.user.email,
                      tier: state.user.tier,
                      pending: document.body.classList.contains('auth-pending'),
                      guestHidden: document.querySelector('#topbar-auth-guest')?.hidden,
                      userHidden: document.querySelector('#topbar-auth-user')?.hidden
                    })""")
                    row = {"route": path, "initial": initial, "hydrated": final}
                    payload["authenticated"].append(row)
                    assert initial["pending"] and initial["guestVisibility"] == "hidden" and initial["userVisibility"] == "hidden", row
                    assert final["email"] == identities["accounts"][0][0] and final["tier"] == "student_pro", row
                    assert final["guestHidden"] and not final["userHidden"] and not final["pending"], row

                # Clear the test cookie to exercise guest hydration on every route too.
                context.clear_cookies()
                for path in routes:
                    response = page.goto(base + path, wait_until="domcontentloaded", timeout=20000)
                    if not response or response.status != 200:
                        raise AssertionError({"route": path, "status": response.status if response else None})
                    initial = page.evaluate("""() => ({
                      pending: document.body.classList.contains('auth-pending'),
                      guestVisibility: getComputedStyle(document.querySelector('#topbar-auth-guest')).visibility,
                      userVisibility: getComputedStyle(document.querySelector('#topbar-auth-user')).visibility
                    })""")
                    page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=12000)
                    final = page.evaluate("""() => ({
                      guest: document.querySelector('#user-name')?.textContent,
                      pending: document.body.classList.contains('auth-pending'),
                      guestHidden: document.querySelector('#topbar-auth-guest')?.hidden,
                      userHidden: document.querySelector('#topbar-auth-user')?.hidden,
                      signInVisible: !!document.querySelector('#topbar-signin-btn')?.getClientRects().length
                    })""")
                    row = {"route": path, "initial": initial, "hydrated": final}
                    payload["signed_out"].append(row)
                    assert initial["pending"] and initial["guestVisibility"] == "hidden" and initial["userVisibility"] == "hidden", row
                    assert final["guest"] == "Guest Explorer" and not final["guestHidden"] and final["userHidden"] and final["signInVisible"], row

                payload["route_count"] = len(routes)
                payload["asset"] = page.locator('script[src*="app.js"]').get_attribute("src")
                payload["result"] = "passed" if not payload["page_errors"] and not payload["console_errors"] else "failed"
                assert payload["asset"] == "/assets/app.js?v=205", payload["asset"]
                assert payload["result"] == "passed", payload
                (OUT / "browser-id168-auth-matrix-v205.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                browser.close()
            print(json.dumps({"result": payload["result"], "route_count": payload["route_count"], "authenticated_checks": len(payload["authenticated"]), "signed_out_checks": len(payload["signed_out"]), "asset": payload["asset"], "page_errors": payload["page_errors"], "console_errors": payload["console_errors"]}, indent=2))
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
