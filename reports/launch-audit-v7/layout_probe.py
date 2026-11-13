from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
PDF = Path(r"C:\Users\mdham\Downloads\notes.pdf")


def layout(page, selectors: list[str]) -> dict[str, dict[str, int | bool]]:
    return page.evaluate(
        """(selectors) => Object.fromEntries(selectors.map(selector => {
          const node = document.querySelector(selector);
          if (!node) return [selector, {present: false}];
          const rect = node.getBoundingClientRect();
          const style = getComputedStyle(node);
          return [selector, {
            present: true,
            visible: !node.hidden && style.display !== 'none' && rect.width > 0 && rect.height > 0,
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.round(rect.width), height: Math.round(rect.height),
            scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
            scrollHeight: node.scrollHeight, clientHeight: node.clientHeight,
          }];
        }))""",
        selectors,
    )


result = {"viewports": [], "page_errors": [], "console_errors": []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    result["chromium_version"] = browser.version
    for width, height, mobile in ((375, 812, True), (1104, 860, False)):
        context = browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile)
        page = context.new_page()
        page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
        page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
        page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
        page.locator("#mob-nav-studio" if mobile else "#tab-studio-view").click()
        page.locator("#studio-file-input").set_input_files(str(PDF))
        expect(page.locator("#studio-page-count")).to_have_text("69", timeout=60000)
        studio = layout(page, [
            "html", "body", "#app-shell", ".main-area", ".dynamic-workspace", "#view-pdf-studio",
            ".pdf-studio", ".studio-main-viewport", ".studio-toolbar", ".studio-primary-ribbon",
            ".studio-sub-ribbon", ".studio-canvas-area", ".studio-mobile-dock", ".app-global-footer",
            ".ephemeral-work-notice",
        ])
        page.locator("#mob-nav-ai" if mobile else "#tab-ai-view").click()
        page.locator("#ai-file-input").set_input_files(str(PDF))
        expect(page.locator("#ai-doc-meta")).to_contain_text("69 pages", timeout=60000)
        ai = layout(page, [
            "html", "body", "#app-shell", ".main-area", ".dynamic-workspace", "#view-ai-studio",
            ".ai-studio-topbar", ".ai-studio-container", ".ai-chat-card", ".ai-engine-notice-bar",
            "#trigger-extract-btn", "#trigger-summary-btn", ".summary-runtime-slot", "#summary-display",
            "#summary-actions-bar", ".app-global-footer", ".ephemeral-work-notice",
        ])
        result["viewports"].append({"width": width, "height": height, "studio_loaded": studio, "ai_loaded": ai})
        context.close()
    browser.close()

(OUT / "layout-before-fix.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
