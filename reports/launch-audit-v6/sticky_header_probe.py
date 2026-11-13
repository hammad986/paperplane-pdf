from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
ROUTES = {
    "ocr": "/ocr-pdf",
    "remove": "/remove-pages-pdf",
    "grayscale": "/convert-pdf-to-grayscale",
    "tool_desk": "/tool-desk",
}
WIDTHS = (375, 1104)


def visible_rect(page, selector: str):
    return page.evaluate(
        """selector => {
          const element = document.querySelector(selector);
          if (!element) return null;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          if (style.display === 'none' || style.visibility === 'hidden' || !rect.width || !rect.height) return null;
          return {x: Math.round(rect.x), y: Math.round(rect.y), right: Math.round(rect.right), bottom: Math.round(rect.bottom), width: Math.round(rect.width), height: Math.round(rect.height)};
        }""",
        selector,
    )


results = []
page_errors = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    for run in (1, 2):
        for route_name, route in ROUTES.items():
            for width in WIDTHS:
                page = context.new_page()
                page.set_viewport_size({"width": width, "height": 812 if width < 900 else 860})
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.add_init_script("localStorage.setItem('paperplane_theme', 'dark')")
                page.goto(f"{BASE}{route}", wait_until="domcontentloaded")
                page.locator(".topbar").wait_for(state="visible")
                page.wait_for_timeout(250)
                selectors = {
                    "topbar": ".topbar",
                    "title": "#tool-title" if route_name != "tool_desk" else "#view-tool-desk-directory h1",
                    "dropzone": ".dropzone",
                    "directory_filters": "#tool-desk-directory-filters",
                }
                for scroll_name, scroll_y in (("top", 0), ("scrolled", 300)):
                    page.evaluate("y => { if (innerWidth <= 900) window.scrollTo(0, y); else { const area = document.querySelector('.main-area'); if (area) area.scrollTop = y; } }", scroll_y)
                    page.wait_for_timeout(120)
                    data = page.evaluate(
                        """selectors => {
                          const rect = selector => {
                            const element = document.querySelector(selector);
                            if (!element) return null;
                            const box = element.getBoundingClientRect();
                            const style = getComputedStyle(element);
                            if (style.display === 'none' || style.visibility === 'hidden' || !box.width || !box.height) return null;
                            return {x: Math.round(box.x), y: Math.round(box.y), right: Math.round(box.right), bottom: Math.round(box.bottom), width: Math.round(box.width), height: Math.round(box.height)};
                          };
                          const boxes = Object.fromEntries(Object.entries(selectors).map(([key, selector]) => [key, rect(selector)]));
                          const header = boxes.topbar;
                          const title = boxes.title;
                          const headerCoversTitle = Boolean(header && title && title.y < header.bottom && title.bottom > header.y && title.x < header.right && title.right > header.x);
                          const filters = document.querySelector('.home-filter-pills');
                          return {
                            viewportWidth: innerWidth,
                            documentWidth: document.documentElement.scrollWidth,
                            bodyWidth: document.body.scrollWidth,
                            scrollX: window.scrollX,
                            scrollY: window.scrollY,
                            mainScrollTop: document.querySelector('.main-area')?.scrollTop || 0,
                            boxes,
                            headerCoversTitle,
                            filterOverflow: filters ? filters.scrollWidth > filters.clientWidth : false,
                            filterLabels: filters ? [...filters.querySelectorAll('.filter-pill')].map(item => ({text: item.innerText.trim(), right: Math.round(item.getBoundingClientRect().right), visible: item.getBoundingClientRect().right <= innerWidth + 1})) : []
                          };
                        }""",
                        selectors,
                    )
                    data.update({"run": run, "route": route_name, "width": width, "scroll": scroll_name})
                    results.append(data)
                    if scroll_name == "top":
                        page.screenshot(path=str(OUT / f"after-sticky-{route_name}-{width}-run-{run}-top.png"))
                    else:
                        page.screenshot(path=str(OUT / f"after-sticky-{route_name}-{width}-run-{run}-scrolled.png"))
                page.close()
    browser.close()

report = {"base": BASE, "routes": ROUTES, "widths": WIDTHS, "results": results, "page_errors": page_errors}
(OUT / "sticky-header-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
