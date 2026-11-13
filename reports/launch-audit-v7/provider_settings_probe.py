from __future__ import annotations

import json
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


BASE = "http://127.0.0.1:8502"
OUT = Path(__file__).resolve().parent
result: dict[str, object] = {"base": BASE, "model_inference_calls": 0, "page_errors": [], "console_errors": []}

with httpx.Client(timeout=10) as client:
    for name, path in (("capabilities", "/api/ai/capabilities"), ("connection_check", "/api/ai/test-connection")):
        response = client.get(f"{BASE}{path}")
        result[name] = {"http_status": response.status_code, "body": response.json()}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1104, "height": 860})
    page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
    page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    page.locator("#tab-ai-view").click()
    expect(page.locator("#view-ai-studio")).to_be_visible()
    expect(page.locator("#trigger-summary-btn")).to_be_disabled()
    expect(page.locator("#sidebar-settings-gear-btn")).to_be_visible()
    page.locator("#sidebar-settings-gear-btn").click()
    page.locator("#settings-tab-btn-privacy").click()
    expect(page.locator("#ai-clear-work-btn")).to_be_visible()
    expect(page.locator("#studio-clear-work-btn")).to_be_visible()
    page.screenshot(path=str(OUT / "provider-unavailable-settings-1104.png"), full_page=True)
    result["summary_button_disabled_without_provider"] = page.locator("#trigger-summary-btn").is_disabled()
    result["clear_work_controls_available_in_privacy_settings"] = {
        "ai": page.locator("#ai-clear-work-btn").is_visible(),
        "studio": page.locator("#studio-clear-work-btn").is_visible(),
    }
    browser.close()

(OUT / "provider-settings-final.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
