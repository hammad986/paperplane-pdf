from __future__ import annotations

import json
from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
        modal = page.locator("#cloud-modal")
        page.locator("#topbar-cloud-btn").click()
        assert modal.is_visible()
        page.keyboard.press("Escape")
        escape_closed = modal.is_hidden()
        page.locator("#topbar-cloud-btn").click()
        assert modal.is_visible()
        page.locator("#cloud-modal").click(position={"x": 10, "y": 10})
        outside_closed = modal.is_hidden()
        page.locator("#topbar-cloud-btn").click()
        blocked_while_open = False
        try:
            page.locator('.home-tool-card[data-select-operation="merge"]').click(timeout=1500)
        except Exception as error:
            blocked_while_open = "intercepts pointer events" in str(error)
        page.keyboard.press("Escape")
        page.locator('.home-tool-card[data-select-operation="merge"]').click(timeout=8000)
        navigated_to_tool = page.url.endswith("/merge-pdf")
        closed_on_navigation = modal.is_hidden()
        result = {
            "escape_closed": escape_closed,
            "outside_click_closed": outside_closed,
            "navigation_blocked_while_open": blocked_while_open,
            "navigation_to_tool_succeeded": navigated_to_tool,
            "closed_on_navigation": closed_on_navigation,
            "page_errors": errors,
        }
        page.screenshot(path="reports/launch-audit-v3/cloud-modal-closed-navigation.png")
        browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert all([escape_closed, outside_closed, blocked_while_open, navigated_to_tool, closed_on_navigation]) and not errors, result


if __name__ == "__main__":
    main()
