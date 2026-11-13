from __future__ import annotations

import json
import time
from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"


def main() -> None:
    result = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        delayed = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        delayed.on("pageerror", lambda error: errors.append(str(error)))
        delayed.add_init_script("""(() => {
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {
            const url = typeof input === 'string' ? input : input.url;
            if (new URL(url, location.href).pathname === '/api/auth/me') {
              return new Promise((resolve, reject) => setTimeout(() => originalFetch(input, init).then(resolve, reject), 2500));
            }
            return originalFetch(input, init);
          };
        })();""")
        delayed.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        delayed.wait_for_timeout(300)
        while_text = delayed.locator("#quota-text").inner_text()
        body_pending_during_delay = delayed.locator("body").get_attribute("class")
        delayed.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
        delayed.wait_for_timeout(2600)
        after_text = delayed.locator("#quota-text").inner_text()
        delayed.screenshot(path="reports/launch-audit-v3/quota-delayed-auth.png", full_page=True)

        failed = browser.new_page(viewport={"width": 1440, "height": 960})
        failed.on("pageerror", lambda error: errors.append(str(error)))
        failed.route("**/api/auth/me", lambda route: route.abort("failed"))
        failed.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        failed.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
        failed_text = failed.locator("#quota-text").inner_text()
        failed.screenshot(path="reports/launch-audit-v3/quota-auth-failure.png", full_page=True)

        no_js_context = browser.new_context(viewport={"width": 1440, "height": 960}, java_script_enabled=False)
        no_js = no_js_context.new_page()
        no_js.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        no_js_text = no_js.locator("#quota-text").inner_text()
        no_js_file_hint = no_js.locator("#file-hint").inner_text()
        no_js.screenshot(path="reports/launch-audit-v3/quota-no-js.png", full_page=True)

        result = {
            "delayed_auth_initial_quota": while_text,
            "body_class_during_delay": body_pending_during_delay,
            "delayed_auth_after_quota": after_text,
            "auth_failure_quota": failed_text,
            "no_js_quota": no_js_text,
            "no_js_file_hint": no_js_file_hint,
            "page_errors": errors,
        }
        browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert "auth-pending" in body_pending_during_delay and "Checking usage" in while_text, result
    assert after_text != "Checking usage…", result
    assert "Checking usage" not in failed_text and "100" in failed_text, result
    assert "100" in no_js_text and "50 MB" in no_js_file_hint and "500 MB" in no_js_file_hint and "100 files" in no_js_file_hint, result
    assert not errors, result


if __name__ == "__main__":
    main()
