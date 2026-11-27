"""Check both processing modes and saved preference across supported PDF tools."""
from __future__ import annotations
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
output = Path(__file__).resolve().parent / "browser-id186-server-local-toggle.json"
routes = ["/merge-pdf", "/split-pdf", "/remove-pages-pdf", "/rotate-pdf"]
errors: list[str] = []
results: list[dict[str, object]] = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.set_default_timeout(10000)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:8767/merge-pdf", wait_until="domcontentloaded")
    page.evaluate("localStorage.removeItem('paperplane-pdf-processing-mode')")
    page.reload(wait_until="domcontentloaded")
    for desired, value in ((False, "server"), (True, "local")):
        for route in routes:
            page.goto(f"http://127.0.0.1:8767{route}", wait_until="domcontentloaded")
            toggle = page.locator("#client-privacy-toggle")
            if toggle.is_disabled():
                raise AssertionError(f"mode switch disabled on {route}")
            if toggle.is_checked() != desired:
                page.locator("#sidebar label.toggle-switch-sm").click()
            page.wait_for_function("expected => document.querySelector('#client-privacy-toggle')?.checked === expected && window.state?.clientSideMode === expected", arg=desired)
            persisted = page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")
            results.append({"route": route, "expected_mode": value, "toggle_checked": toggle.is_checked(), "toggle_enabled": not toggle.is_disabled(), "persisted_preference": persisted, "runtime_mode": page.evaluate("window.state?.clientSideMode")})
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("expected => document.querySelector('#client-privacy-toggle')?.checked === expected && window.state?.clientSideMode === expected", arg=desired)
            results[-1]["restored_after_reload"] = toggle.is_checked() == desired and page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')") == value
    browser.close()
result = {"build": "app.js v191", "preference_key": "paperplane-pdf-processing-mode", "routes": routes, "checks": results, "browser_errors": errors, "passed": len(results) == len(routes) * 2 and all(row["toggle_checked"] == (row["expected_mode"] == "local") and row["toggle_enabled"] and row["persisted_preference"] == row["expected_mode"] and row["runtime_mode"] == (row["expected_mode"] == "local") and row["restored_after_reload"] for row in results) and not errors}
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))