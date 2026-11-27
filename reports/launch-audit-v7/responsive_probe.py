from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8502"
PDF = Path(r"C:\Users\mdham\Downloads\notes.pdf")
MOBILE_WIDTHS = (360, 375, 768)
DESKTOP_WIDTHS = (1104, 1366, 1920)
HEIGHTS = {360: 780, 375: 812, 768: 1024, 1104: 860, 1366: 900, 1920: 1080}


def collect(page, view: str, state: str, width: int, theme: str) -> dict:
    selectors = [
        "html", "body", "#app-shell", ".main-area", ".dynamic-workspace",
        "#view-pdf-studio", ".pdf-studio", ".studio-thumbnails-bar",
        ".studio-toolbar", ".studio-primary-ribbon", ".studio-sub-ribbon",
        ".studio-canvas-area", ".studio-mobile-dock", ".studio-mobile-page-actions",
        ".app-global-footer", "#view-ai-studio", ".ai-studio-topbar",
        ".ai-studio-container", ".ai-studio-container > div:last-child",
        ".ai-studio-container > div:last-child > .ai-chat-card:first-child",
        ".ai-studio-container > div:last-child > .ai-chat-card:last-child",
        ".ai-chat-card", "#trigger-extract-btn",
        ".extract-runtime-slot", "#trigger-summary-btn", ".summary-runtime-slot",
        "#summary-display", ".summary-actions-slot", ".ephemeral-work-notice",
        "#ai-engine-notice-bar",
    ]
    geometry = page.evaluate(
        """(selectors) => Object.fromEntries(selectors.map(selector => {
          const node = document.querySelector(selector);
          if (!node) return [selector, {present: false}];
          const rect = node.getBoundingClientRect();
          const style = getComputedStyle(node);
          const visible = !node.hidden && style.display !== 'none' && rect.width > 0 && rect.height > 0;
          return [selector, {
            present: true, visible,
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.round(rect.width), height: Math.round(rect.height),
            scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
            scrollHeight: node.scrollHeight, clientHeight: node.clientHeight,
            clippedRight: visible && rect.right > window.innerWidth + 1,
            clippedLeft: visible && rect.left < -1
          }];
        }))""",
        selectors,
    )
    return {
        "view": view,
        "state": state,
        "width": width,
        "height": HEIGHTS[width],
        "theme": theme,
        "document_width": page.evaluate("document.documentElement.scrollWidth"),
        "body_width": page.evaluate("document.body.scrollWidth"),
        "geometry": geometry,
    }


def set_theme(page, theme: str) -> None:
    page.evaluate(
        """theme => {
          document.body.classList.toggle('light-mode', theme === 'light');
          document.body.classList.toggle('dark-mode', theme === 'dark');
        }""",
        theme,
    )


def screenshot(page, view: str, state: str, width: int, theme: str) -> None:
    page.screenshot(path=str(OUT / f"layout-v7-{view}-{state}-{width}-{theme}.png"), full_page=True)


def run_context(browser, mobile: bool, widths: tuple[int, ...], result: dict) -> None:
    initial = widths[0]
    context = browser.new_context(
        viewport={"width": initial, "height": HEIGHTS[initial]},
        is_mobile=mobile,
        has_touch=mobile,
        device_scale_factor=1,
        accept_downloads=True,
    )
    page = context.new_page()
    page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
    page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    page.locator("#mob-nav-studio" if mobile else "#tab-studio-view").click()

    studio_states: list[str] = ["empty"]
    for theme in ("dark", "light"):
        set_theme(page, theme)
        for width in widths:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            page.wait_for_timeout(120)
            metric = collect(page, "studio", "empty", width, theme)
            result["runs"].append(metric)
            if width in (375, 1104):
                screenshot(page, "studio", "empty", width, theme)

    page.locator("#studio-file-input").set_input_files(str(PDF))
    expect(page.locator("#studio-page-count")).to_have_text("69", timeout=90000)
    expect(page.locator('#studio-page-stack .studio-page-sheet[data-page="1"] .studio-page-loading')).to_be_hidden(timeout=90000)
    page.wait_for_timeout(4100)  # Let the transient successful-load toast leave the captured view.
    studio_states.append("loaded")
    for theme in ("dark", "light"):
        set_theme(page, theme)
        for width in widths:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            page.wait_for_timeout(180)
            metric = collect(page, "studio", "loaded", width, theme)
            result["runs"].append(metric)
            if width in (375, 1104):
                screenshot(page, "studio", "loaded", width, theme)

    if mobile:
        page.set_viewport_size({"width": 375, "height": HEIGHTS[375]})
        page.locator("#studio-mobile-pages-btn").click()
        page.wait_for_timeout(100)
        drawer = collect(page, "studio", "pages-drawer-open", 375, "light")
        drawer["page_action_buttons"] = page.locator("#studio-mobile-page-actions-slot .studio-tool-btn").count()
        result["runs"].append(drawer)
        page.locator("#studio-mobile-pages-close").click()

    page.locator("#mob-nav-ai" if mobile else "#tab-ai-view").click()
    for theme in ("dark", "light"):
        set_theme(page, theme)
        for width in widths:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            page.wait_for_timeout(120)
            metric = collect(page, "ai", "empty", width, theme)
            result["runs"].append(metric)
            if width in (375, 1104):
                screenshot(page, "ai", "empty", width, theme)

    page.locator("#ai-file-input").set_input_files(str(PDF))
    expect(page.locator("#ai-doc-meta")).to_contain_text("69 pages", timeout=60000)
    page.wait_for_timeout(4100)
    for theme in ("dark", "light"):
        set_theme(page, theme)
        for width in widths:
            page.set_viewport_size({"width": width, "height": HEIGHTS[width]})
            page.wait_for_timeout(150)
            metric = collect(page, "ai", "loaded", width, theme)
            result["runs"].append(metric)
            if width in (375, 1104):
                screenshot(page, "ai", "loaded", width, theme)

    context.close()


result = {
    "base": BASE,
    "input_pdf": {"filename": PDF.name, "bytes": PDF.stat().st_size},
    "runs": [],
    "page_errors": [],
    "console_errors": [],
}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    result["chromium_version"] = browser.version
    run_context(browser, True, MOBILE_WIDTHS, result)
    run_context(browser, False, DESKTOP_WIDTHS, result)
    browser.close()

result["all_document_widths_match"] = all(
    row["document_width"] == row["width"] and row["body_width"] == row["width"]
    for row in result["runs"]
)
stable_selectors = {
    "studio": [".pdf-studio", ".studio-toolbar", ".studio-primary-ribbon", ".studio-sub-ribbon", ".studio-canvas-area", ".studio-mobile-dock"],
    "ai": [".ai-studio-topbar", ".ai-studio-container", ".ai-chat-card", ".ai-studio-container > div:last-child", ".ai-studio-container > div:last-child > .ai-chat-card:first-child", ".ai-studio-container > div:last-child > .ai-chat-card:last-child", "#trigger-extract-btn", ".extract-runtime-slot", "#trigger-summary-btn", ".summary-runtime-slot", "#summary-display"],
}
result["empty_loaded_geometry_mismatches"] = []
for view, selectors in stable_selectors.items():
    candidates = [row for row in result["runs"] if row["view"] == view and row["state"] in ("empty", "loaded")]
    keys = {(row["width"], row["theme"]) for row in candidates}
    for width, theme in keys:
        pair = {row["state"]: row for row in candidates if row["width"] == width and row["theme"] == theme}
        if set(pair) != {"empty", "loaded"}:
            continue
        for selector in selectors:
            empty = pair["empty"]["geometry"].get(selector, {})
            loaded = pair["loaded"]["geometry"].get(selector, {})
            empty_rect = tuple(empty.get(key) for key in ("x", "y", "width", "height", "visible"))
            loaded_rect = tuple(loaded.get(key) for key in ("x", "y", "width", "height", "visible"))
            if empty_rect != loaded_rect:
                result["empty_loaded_geometry_mismatches"].append({"view": view, "width": width, "theme": theme, "selector": selector, "empty": empty_rect, "loaded": loaded_rect})
result["visible_elements_clipped"] = [
    {"view": row["view"], "state": row["state"], "width": row["width"], "theme": row["theme"], "selector": selector, **element}
    for row in result["runs"]
    for selector, element in row["geometry"].items()
    if element.get("visible") and (element.get("clippedRight") or element.get("clippedLeft"))
]
(OUT / "responsive-final.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({
    "chromium_version": result["chromium_version"],
    "runs": len(result["runs"]),
    "all_document_widths_match": result["all_document_widths_match"],
    "empty_loaded_geometry_mismatch_count": len(result["empty_loaded_geometry_mismatches"]),
    "visible_elements_clipped_count": len(result["visible_elements_clipped"]),
    "page_errors": result["page_errors"],
    "console_errors": result["console_errors"],
    "report": "responsive-final.json",
}, indent=2, ensure_ascii=False))
