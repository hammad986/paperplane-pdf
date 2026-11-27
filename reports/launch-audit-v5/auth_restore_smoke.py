from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
EMAIL = "launch-audit@example.test"
ROUTES = ["/", "/tool-desk", "/merge-pdf", "/studio", "/download"]
MOCK_AUTH = {
    "authenticated": True,
    "email": EMAIL,
    "tier": "free",
    "is_pro": False,
    "is_dev": False,
    "usage_today": 6,
    "daily_limit": 100,
}


def wait_for(page, expression: str, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.evaluate(f"() => Boolean({expression})"):
            return True
        time.sleep(0.05)
    return False


def main() -> None:
    evidence: list[dict[str, object]] = []
    console_errors: list[dict[str, str]] = []
    operations_responses: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.on("pageerror", lambda error: console_errors.append({"kind": "page", "text": str(error)}))
        page.on("console", lambda message: console_errors.append({"kind": "console", "text": message.text}) if message.type == "error" else None)
        page.on("response", lambda response: operations_responses.append({"status": response.status, "url": response.url}) if "/api/operations" in response.url else None)
        page.add_init_script(f"""(() => {{
          sessionStorage.setItem('paperplane-last-auth-shell-email', {json.dumps(EMAIL)});
          window.__auditAuthResponse = {json.dumps(MOCK_AUTH)};
          window.__authQueue = [];
          const nativeFetch = window.fetch.bind(window);
          window.__releaseAuth = () => window.__authQueue.splice(0).forEach(
            ({{resolve}}) => resolve(new Response(JSON.stringify(window.__auditAuthResponse), {{
              status:200, headers:{{'Content-Type':'application/json'}}
            }}))
          );
          window.fetch = (resource, init={{}}) => String(resource).includes('/api/auth/me')
            ? new Promise(resolve => window.__authQueue.push({{resolve}}))
            : nativeFetch(resource, init);
        }})()""")

        for index, route in enumerate(ROUTES, start=1):
            previous_operations_responses = len(operations_responses)
            page.goto(BASE + route, wait_until="domcontentloaded", timeout=30000)
            if not wait_for(page, "window.__authQueue?.length > 0"):
                raise RuntimeError(f"Auth endpoint was not held on {route}")
            pending = page.evaluate(
                """() => {
                  const user=document.querySelector('#topbar-auth-user');
                  const guest=document.querySelector('#topbar-auth-guest');
                  const quota=document.querySelector('#quota-text')?.textContent.trim() || '';
                  return {
                    route:location.pathname,
                    cached_email:document.querySelector('#topbar-username')?.textContent.trim(),
                    user_hidden:user?.hidden,
                    user_visibility:getComputedStyle(user).visibility,
                    user_visible:Boolean(user && !user.hidden && getComputedStyle(user).visibility==='visible' && user.getBoundingClientRect().width>0),
                    guest_hidden:guest?.hidden,
                    guest_text:guest?.innerText.trim(),
                    auth_pending:document.body.classList.contains('auth-pending'),
                    quota_text:quota,
                    quota_has_loading_copy:/checking usage/i.test(quota)
                  };
                }"""
            )
            if index == 1:
                page.screenshot(path=str(OUT / "auth-restore-pending-375.png"), full_page=False)
            page.evaluate("window.__releaseAuth()")
            if not wait_for(page, f"!document.body.classList.contains('auth-pending') && document.querySelector('#topbar-username')?.textContent.trim() === {json.dumps(EMAIL)}"):
                raise RuntimeError(f"Mock auth response did not settle on {route}")
            deadline = time.monotonic() + 15
            while len(operations_responses) <= previous_operations_responses and time.monotonic() < deadline:
                time.sleep(0.05)
            settled = page.evaluate(
                """() => ({
                  user_visible:!document.querySelector('#topbar-auth-user')?.hidden,
                  guest_hidden:document.querySelector('#topbar-auth-guest')?.hidden,
                  email:document.querySelector('#topbar-username')?.textContent.trim(),
                  quota_text:document.querySelector('#quota-text')?.textContent.trim(),
                  auth_restoring:document.body.classList.contains('auth-restoring')
                })"""
            )
            evidence.append({"cycle": index, "route": route, "pending": pending, "settled": settled})

        browser.close()

    result = {
        "identity": EMAIL,
        "routes": ROUTES,
        "cycles": evidence,
        "console_or_page_errors": console_errors,
        "operations_responses": operations_responses,
        "screenshot": str(OUT / "auth-restore-pending-375.png"),
        "auth_contract": "The cached email is only a same-tab display hint; every cycle waits for a mocked authenticated API response before the app applies an authenticated state or quota.",
    }
    target = OUT / "auth-restore-smoke.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(target), **result}, indent=2, ensure_ascii=False))
    if console_errors or len(operations_responses) != len(ROUTES) or any(response["status"] != 200 for response in operations_responses) or any(not cycle["pending"]["user_visible"] or not cycle["pending"]["guest_hidden"] or cycle["pending"]["quota_has_loading_copy"] or cycle["settled"]["email"] != EMAIL or not cycle["settled"]["guest_hidden"] for cycle in evidence):
        raise SystemExit("Auth shell or quota transient-state check failed")


if __name__ == "__main__":
    main()
