from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8501"
REPORT_DIR = ROOT / "reports" / "launch-audit-v4"
WIDTHS = [333, 375, 414, 768, 1024, 1366, 1920]
ROUTES = ["/", "/download", "/privacy", "/terms", "/api-docs"]


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    browser_errors: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
        )
        for route in ROUTES:
            for width in WIDTHS:
                page = browser.new_page(
                    viewport={"width": width, "height": 900},
                    color_scheme="light",
                )
                page.on("pageerror", lambda error, p=page: browser_errors.append({"url": p.url, "type": "pageerror", "message": str(error)}))
                page.on(
                    "console",
                    lambda message, p=page: browser_errors.append({"url": p.url, "type": "console", "message": message.text})
                    if message.type == "error" and ("content security policy" in message.text.lower() or "refused to" in message.text.lower())
                    else None,
                )
                response = page.goto(BASE_URL + route, wait_until="domcontentloaded")
                page.wait_for_timeout(150)
                metrics = page.evaluate(
                    """() => {
                      const candidates = [...document.querySelectorAll('#view-api-docs .view-header-bar, #view-api-docs .view-header-title, #view-api-docs .view-header-actions, #view-api-docs .api-docs-hero-box, #view-api-docs .api-docs-meta-grid, #view-api-docs .api-meta-item, #view-api-docs .api-docs-tabs, #view-api-docs .api-code-workbench-header, #view-api-docs .btn-copy-code')];
                      const visibleOverflow = candidates.map(el => { const r=el.getBoundingClientRect(); return {selector:el.className || el.tagName,left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width)}; }).filter(r => r.right > innerWidth + 1 || r.left < -1);
                      return {
                      width: innerWidth,
                      documentWidth: document.documentElement.scrollWidth,
                      bodyWidth: document.body.scrollWidth,
                      documentHeight: document.documentElement.scrollHeight,
                      bodyClass: document.body.className,
                      visibleOverflow
                    }}"""
                )
                entry = {
                    "route": route,
                    "status": response.status if response else None,
                    **metrics,
                }
                results.append(entry)
                if route == "/api-docs" and width in (333, 375, 1366):
                    page.screenshot(path=str(REPORT_DIR / f"post-api-docs-{width}.png"))
                page.close()
        browser.close()

    overflows = [row for row in results if row["bodyWidth"] > row["width"] or row["documentWidth"] > row["width"]]
    non200 = [row for row in results if row["status"] != 200]
    report = {
        "routes": len(ROUTES),
        "widths": WIDTHS,
        "checks": len(results),
        "overflows": overflows,
        "non200": non200,
        "browserErrors": browser_errors,
        "results": results,
    }
    out = REPORT_DIR / "site-route-layout-results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "checks": len(results), "overflows": len(overflows), "non200": len(non200), "browserErrors": len(browser_errors)}, indent=2))


if __name__ == "__main__":
    main()
