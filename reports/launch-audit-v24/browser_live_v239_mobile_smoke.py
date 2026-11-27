"""Read-only deployed mobile layout smoke on one installed Chrome instance."""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "https://paperplane.qd.je"
ROUTES = ("/", "/merge-pdf", "/studio", "/ai-intelligence")


def main() -> None:
    evidence = {"base": BASE, "checks": [], "page_errors": [], "console_errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(service_workers="block")
        page = context.new_page()
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
        page.on("console", lambda message: evidence["console_errors"].append(message.text)
                if message.type == "error" and "Failed to load resource" not in message.text else None)
        for width in (320, 390):
            page.set_viewport_size({"width": width, "height": 844})
            for route in ROUTES:
                response = page.goto(BASE + route, wait_until="domcontentloaded", timeout=30000)
                page.locator("body").wait_for(state="visible")
                page.wait_for_timeout(400)
                measured = page.evaluate("""() => ({
                    width: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    bodyWidth: document.body.scrollWidth,
                    title: document.title,
                    mainVisible: !!document.querySelector('main'),
                    runButton: (() => { const el = document.querySelector('#run-button');
                      if (!el) return null; const r = el.getBoundingClientRect();
                      return {left:r.left,right:r.right,width:r.width}; })()
                })""")
                measured.update({"route": route, "status": response.status if response else None,
                                 "horizontal_overflow": max(measured["documentWidth"], measured["bodyWidth"]) > width + 1})
                page.screenshot(path=str(OUT / f"live-v239-{route.strip('/').replace('/', '-') or 'home'}-{width}.png"))
                evidence["checks"].append(measured)
        browser.close()
    evidence["passed"] = all(check["status"] == 200 and not check["horizontal_overflow"]
                             and check["mainVisible"] for check in evidence["checks"])
    evidence["passed"] &= not evidence["page_errors"] and not evidence["console_errors"]
    (OUT / "browser-live-v239-mobile-smoke.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
