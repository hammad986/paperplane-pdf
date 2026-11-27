"""Check settings dialog bounds and tab strip at narrow phone widths."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent / "browser-id80-settings-mobile-bounds.json"
errors: list[str] = []
measurements: list[dict[str, object]] = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width in (320, 360, 390):
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto("http://127.0.0.1:8766/", wait_until="domcontentloaded")
        page.locator("#mobile-menu-btn").click()
        page.locator("#sidebar-settings-gear-btn").click()
        page.wait_for_timeout(500)
        for tab in ("account", "privacy"):
            if tab == "privacy":
                page.evaluate("window.switchSettingsTab('privacy')")
                page.wait_for_timeout(500)
            measurements.append(page.evaluate("""() => {
              const card = document.querySelector('#settings-modal .settings-modal-card').getBoundingClientRect();
              const rail = document.querySelector('#settings-modal .settings-tabs');
              const active = document.querySelector('#settings-modal .settings-tab-btn.active').getBoundingClientRect();
              const pane = document.querySelector('#settings-modal .settings-pane:not([hidden])').getBoundingClientRect();
              return {
                width: innerWidth,
                tab: document.querySelector('#settings-modal .settings-tab-btn.active').dataset.tab,
                cardWithinViewport: card.left >= 0 && card.right <= innerWidth + 1,
                activeTabInsideViewport: active.left >= 0 && active.right <= innerWidth + 1,
                activeTabInsideRail: active.left >= rail.getBoundingClientRect().left - 1 && active.right <= rail.getBoundingClientRect().right + 1,
                activePaneWithinViewport: pane.left >= 0 && pane.right <= innerWidth + 1,
                documentNoHorizontalOverflow: document.documentElement.scrollWidth <= innerWidth
              };
            }"""))
        build = page.evaluate("[...document.scripts].map(s => s.src).find(s => s.includes('/assets/app.js?'))")
        page.close()
    browser.close()
result = {
    "build": build,
    "viewports": [320, 360, 390],
    "tabs_tested": ["account", "privacy"],
    "measurements": measurements,
    "browser_errors": errors,
    "passed": len(measurements) == 6 and all(all(v for k, v in row.items() if k not in ("width", "tab")) for row in measurements) and not errors,
}
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
