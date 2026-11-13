from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
result = {"viewport": 375, "states": {}, "pageErrors": [], "consoleErrors": []}


def wait_for_app(page):
    page.locator("#tool-desk-tools-catalog .home-tool-card").first.wait_for(state="attached", timeout=60_000)


def open_sidebar(page):
    page.locator("#mobile-menu-btn").click()
    page.locator("#sidebar.mobile-open").wait_for(state="visible", timeout=5_000)
    page.wait_for_timeout(450)


def profile_is_clear_of_navigation(page):
    return page.evaluate("""() => {
      const profile = document.querySelector('#sidebar .profile-card-row').getBoundingClientRect();
      const navigation = document.querySelector('.mobile-workspace-bar').getBoundingClientRect();
      return {profileTop: Math.round(profile.top), profileBottom: Math.round(profile.bottom),
        navigationTop: Math.round(navigation.top), clear: profile.bottom <= navigation.top};
    }""")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("pageerror", lambda error: result["pageErrors"].append(str(error)))
    page.on("console", lambda message: result["consoleErrors"].append(message.text) if message.type == "error" else None)

    page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
    page.locator("#tool-title").wait_for(state="visible")
    wait_for_app(page)
    open_sidebar(page)
    local_toggle = page.locator("#client-privacy-toggle")
    assert not local_toggle.is_disabled()
    merge_profile = profile_is_clear_of_navigation(page)
    assert merge_profile["clear"], merge_profile
    page.locator(".footer-privacy-row .toggle-switch-sm").click()
    page.wait_for_timeout(100)
    assert local_toggle.is_checked()
    assert page.locator("#privacy-mode-label").inner_text().strip() == "Local Processing"
    page.screenshot(path=str(OUT / "after-local-processing-supported-375.png"))
    result["states"]["merge"] = {
        "disabled": local_toggle.is_disabled(),
        "checked": local_toggle.is_checked(),
        "label": page.locator("#privacy-mode-label").inner_text().strip(),
        "helper": page.locator("#privacy-mode-support").inner_text().strip(),
        "sidebarWidth": page.locator("#sidebar").evaluate("element => Math.round(element.getBoundingClientRect().width)"),
        "profileClearOfBottomNavigation": merge_profile,
    }

    page.goto(f"{BASE}/translate-pdf", wait_until="domcontentloaded")
    page.locator("#tool-title").wait_for(state="visible")
    wait_for_app(page)
    open_sidebar(page)
    server_toggle = page.locator("#client-privacy-toggle")
    assert server_toggle.is_disabled()
    assert not server_toggle.is_checked()
    translate_profile = profile_is_clear_of_navigation(page)
    assert translate_profile["clear"], translate_profile
    assert page.locator("#privacy-mode-support").inner_text().strip() == "This tool runs on the server"
    page.screenshot(path=str(OUT / "after-local-processing-server-only-375.png"))
    rejection = page.evaluate("""() => {
      setClientSideMode(true);
      return {enabled: state.clientSideMode, checked: document.querySelector('#client-privacy-toggle').checked,
        message: document.querySelector('.toast-notice')?.textContent.trim() || ''};
    }""")
    assert rejection["enabled"] is False and rejection["checked"] is False
    assert "uses server processing" in rejection["message"].lower()
    result["states"]["translate"] = {
        "disabled": server_toggle.is_disabled(),
        "checked": server_toggle.is_checked(),
        "helper": page.locator("#privacy-mode-support").inner_text().strip(),
        "forcedEnable": rejection,
        "sidebarWidth": page.locator("#sidebar").evaluate("element => Math.round(element.getBoundingClientRect().width)"),
        "profileClearOfBottomNavigation": translate_profile,
    }

    result["documentWidth"] = page.evaluate("document.documentElement.scrollWidth")
    result["bodyWidth"] = page.evaluate("document.body.scrollWidth")
    context.close()
    browser.close()

(OUT / "local-processing-mobile-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False))
