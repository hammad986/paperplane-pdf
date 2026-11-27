import json
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8774"


def main():
    state = {"logged_out": False}
    errors = {"page": [], "console": [], "expected_auth_401_console": []}
    evidence = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda error: errors["page"].append(str(error)))
        def capture_console(message):
            if message.type != "error":
                return
            if "status of 401 (Unauthorized)" in message.text:
                errors["expected_auth_401_console"].append(message.text)
            else:
                errors["console"].append(message.text)

        page.on("console", capture_console)

        def route_api(route):
            url = route.request.url
            if url.endswith("/api/auth/me"):
                if state["logged_out"]:
                    route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}')
                else:
                    route.fulfill(status=200, content_type="application/json", body=json.dumps({
                        "authenticated": True,
                        "user_id": "browser-auth-fixture",
                        "email": "fixture@example.invalid",
                        "tier": "free",
                        "tier_label": "Free",
                        "plan_limits": {
                            "free_operations_per_day": 10,
                            "guest_max_file_size_mb": 50,
                            "free_max_file_size_mb": 500,
                            "exam_pass_max_file_size_mb": 500,
                            "pro_max_file_size_mb": 500,
                            "platform_max_file_size_mb": 500,
                            "authenticated": 1,
                            "max_batch_files": 10,
                        },
                    }))
            elif url.endswith("/api/auth/logout"):
                state["logged_out"] = True
                route.fulfill(status=200, content_type="application/json", body='{"ok":true}')
            elif url.endswith("/api/billing/status"):
                route.fulfill(status=401, content_type="application/json", body='{"detail":"Not authenticated"}')
            else:
                route.continue_()

        page.route("**/api/auth/me", route_api)
        page.route("**/api/auth/logout", route_api)
        page.route("**/api/billing/status", route_api)
        page.goto(f"{BASE}/", wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#topbar-auth-user')?.hidden === false")
        evidence["signed_in"] = page.evaluate("""() => ({
          userText: document.querySelector('#topbar-username')?.textContent,
          guestControlsHidden: document.querySelector('#topbar-auth-guest')?.hidden,
          signInVisible: !!document.querySelector('#topbar-signin-btn')?.getClientRects().length
        })""")
        page.locator("#topbar-user-profile-btn").click()
        page.locator("#settings-modal").wait_for(state="visible")
        page.locator("#settings-signout-btn").click()
        page.wait_for_function("document.querySelector('#topbar-auth-guest')?.hidden === false")
        evidence["after_signout"] = page.evaluate("""() => ({
          guestControlsHidden: document.querySelector('#topbar-auth-guest')?.hidden,
          userControlsHidden: document.querySelector('#topbar-auth-user')?.hidden,
          userText: document.querySelector('#topbar-username')?.textContent,
          signInVisible: !!document.querySelector('#topbar-signin-btn')?.getClientRects().length,
          authShellEmail: sessionStorage.getItem('paperplane-last-auth-shell-email'),
          authenticated: !!state.user
        })""")
        page.screenshot(path=str(OUT / "browser-id197-198-auth-signout-390.png"), full_page=True)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("document.querySelector('#topbar-auth-guest')?.hidden === false")
        evidence["after_reload_401"] = page.evaluate("""() => ({
          guestControlsHidden: document.querySelector('#topbar-auth-guest')?.hidden,
          userControlsHidden: document.querySelector('#topbar-auth-user')?.hidden,
          signInVisible: !!document.querySelector('#topbar-signin-btn')?.getClientRects().length,
          userText: document.querySelector('#topbar-username')?.textContent,
          authenticated: !!state.user
        })""")
        evidence["browser_errors"] = errors
        evidence["asset"] = page.locator('script[src*="app.js"]').get_attribute("src")
        browser.close()

    assert evidence["signed_in"]["guestControlsHidden"] is True
    assert evidence["signed_in"]["signInVisible"] is False
    assert evidence["after_signout"]["guestControlsHidden"] is False
    assert evidence["after_signout"]["userControlsHidden"] is True
    assert evidence["after_signout"]["signInVisible"] is True
    assert evidence["after_signout"]["authShellEmail"] is None
    assert evidence["after_reload_401"]["guestControlsHidden"] is False
    assert evidence["after_reload_401"]["userControlsHidden"] is True
    assert evidence["after_reload_401"]["signInVisible"] is True
    assert not errors["page"] and not errors["console"], errors
    (OUT / "browser-id197-198-auth-signout.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
