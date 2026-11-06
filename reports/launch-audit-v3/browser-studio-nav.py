from __future__ import annotations

import json
from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
CASES = [
    ("home", "/"),
    ("merge", "/merge-pdf"),
    ("grayscale", "/convert-pdf-to-grayscale"),
    ("ocr", "/ocr-pdf"),
    ("rotate", "/rotate-pdf"),
    ("remove", "/remove-pages-pdf"),
]


def main() -> None:
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for name, route in CASES:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE + route, wait_until="domcontentloaded", timeout=20_000)
            page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
            assert page.locator("#tab-studio-view").is_visible()
            page.locator("#tab-studio-view").click()
            page.locator("#view-pdf-studio").wait_for(state="visible", timeout=10_000)
            result = {
                "start": name,
                "source_url": route,
                "landing_url": page.url.replace(BASE, ""),
                "studio_visible": not page.locator("#view-pdf-studio").evaluate("el => el.hidden"),
                "legacy_tool_desk_tab": page.locator("#tab-desk-view").count(),
                "tool_workflow_hidden": page.locator("#view-tool-desk").evaluate("el => el.hidden"),
                "page_errors": errors,
            }
            results.append(result)
            if name == "home":
                page.screenshot(path="reports/launch-audit-v3/studio-nav-from-home.png", full_page=True)
            assert result["studio_visible"] and result["legacy_tool_desk_tab"] == 0 and result["tool_workflow_hidden"] and not errors, result
            page.close()
        browser.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
