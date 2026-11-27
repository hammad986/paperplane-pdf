"""Exercise each app waitlist CTA against the local production image."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent / "browser-id56-waitlist-links.json"
platforms = ["windows", "macos", "linux", "android", "ios"]
errors: list[str] = []
checks: list[dict[str, object]] = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:8766/download", wait_until="networkidle")
    for platform in platforms:
        page.locator(f'.btn-platform-join[data-platform="{platform}"]').click()
        checks.append({
            "platform": platform,
            "form_visible": page.locator("#waitlist-form").is_visible(),
            "platform_selected": page.locator("#waitlist-platform").input_value() == platform,
            "email_focused": page.locator("#waitlist-email").evaluate("e => document.activeElement === e"),
            "email_required": page.locator("#waitlist-email").get_attribute("required") is not None,
        })
    build = page.evaluate("[...document.scripts].map(s => s.src).find(s => s.includes('/assets/app.js?'))")
    browser.close()
result = {
    "build": build,
    "route": "/download",
    "viewport": {"width": 390, "height": 844},
    "platform_checks": checks,
    "browser_errors": errors,
    "passed": all(all(v for k, v in row.items() if k != "platform") for row in checks) and len(checks) == len(platforms) and not errors,
}
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
