from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"


def main() -> None:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 360, "height": 812})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def delay_operation_catalog(route):
            response = route.fetch()
            time.sleep(1.2)
            route.fulfill(response=response)

        page.route("**/api/operations", delay_operation_catalog)
        page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        page.locator("#mob-nav-ai").click()
        page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(
            state="attached",
            timeout=20_000,
        )
        page.wait_for_timeout(100)
        state = page.evaluate("""() => ({
          aiHidden: document.querySelector('#view-ai-studio').hidden,
          activeView: sessionStorage.getItem('paperplane-active-view'),
          route: location.pathname,
          width: innerWidth,
          theme: document.body.classList.contains('dark-mode') ? 'dark' : 'light',
          pageErrors: []
        })""")
        state["pageErrors"] = errors
        page.screenshot(path="reports/launch-audit-v3/startup-navigation-race.png", full_page=True)
        browser.close()

    print(json.dumps(state, ensure_ascii=False, indent=2))
    if state["aiHidden"] or state["activeView"] != "ai" or errors:
        raise SystemExit("Startup replaced the user's selected workspace view or raised a page error.")


if __name__ == "__main__":
    Path("reports/launch-audit-v3").mkdir(parents=True, exist_ok=True)
    main()
