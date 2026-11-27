"""Regression check for Escape closing only the topmost/focused overlay."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent / "browser-id84-escape-stack.json"
errors: list[str] = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:8766/", wait_until="networkidle")
    page.locator("#sidebar-settings-gear-btn").click()
    page.keyboard.press("Control+k")
    before = {
        "settings_open": page.locator("#settings-modal").is_visible(),
        "command_palette_open": page.locator("#command-modal").is_visible(),
        "focus_inside_command_palette": page.locator("#command-modal").evaluate("e => e.contains(document.activeElement)"),
    }
    page.keyboard.press("Escape")
    first_escape = {
        "settings_remained_open": page.locator("#settings-modal").is_visible(),
        "command_palette_closed": page.locator("#command-modal").is_hidden(),
    }
    page.keyboard.press("Escape")
    second_escape = {
        "settings_closed": page.locator("#settings-modal").is_hidden(),
        "command_palette_remained_closed": page.locator("#command-modal").is_hidden(),
    }
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#mobile-menu-btn").click()
    drawer_open = page.locator("#sidebar").evaluate("e => e.classList.contains('mobile-open')")
    page.keyboard.press("Escape")
    drawer_escape = {
        "drawer_open_before_escape": drawer_open,
        "drawer_closed": not page.locator("#sidebar").evaluate("e => e.classList.contains('mobile-open')"),
        "backdrop_hidden": page.locator("#mobile-backdrop").is_hidden(),
    }
    result = {
        "build_asset": page.evaluate("[...document.scripts].map(s => s.src).find(s => s.includes('/assets/app.js?'))"),
        "before": before,
        "first_escape": first_escape,
        "second_escape": second_escape,
        "mobile_drawer_escape": drawer_escape,
        "page_errors": errors,
        "passed": all(before.values()) and all(first_escape.values()) and all(second_escape.values()) and all(drawer_escape.values()) and not errors,
    }
    browser.close()
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
