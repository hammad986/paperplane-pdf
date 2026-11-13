from __future__ import annotations

import json
from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
        catalog_card = page.locator('[data-select-operation="translate"] .home-status-badge').inner_text()
        page.goto(BASE + "/translate-pdf", wait_until="domcontentloaded", timeout=20_000)
        page.locator("#tool-availability-notice").wait_for(state="visible", timeout=20_000)
        result = {
            "catalog_status": catalog_card,
            "tool_title": page.locator("#tool-title").inner_text(),
            "unavailable_notice": page.locator("#tool-availability-notice").inner_text(),
            "file_picker_disabled": page.locator("#file-input").is_disabled(),
            "browse_button_disabled": page.locator("#browse").is_disabled(),
            "run_button_disabled": page.locator("#run-button").is_disabled(),
            "page_errors": errors,
        }
        page.screenshot(path="reports/launch-audit-v3/translation-unavailable.png", full_page=True)
        browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert "Requires the Paperplane AI translation service" in result["catalog_status"]
    assert "currently unavailable" in result["unavailable_notice"]
    assert result["file_picker_disabled"] and result["browse_button_disabled"] and result["run_button_disabled"]
    assert not result["page_errors"]


if __name__ == "__main__":
    main()
