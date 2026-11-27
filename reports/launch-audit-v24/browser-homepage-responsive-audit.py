"""Inspect the Tool Desk home directory at phone, tablet, and desktop sizes."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    errors: list[str] = []
    records: list[dict] = []
    with TemporaryDirectory(prefix="paperplane-v24-home-layout-") as tmp:
        app, base, _ = helper.start_server(Path(tmp) / "data")
        try:
            import socket
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not become ready")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                for width, height in ((320, 720), (360, 800), (390, 844), (820, 1180), (1366, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    response = page.goto(base + "/", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(250)
                    sample = page.evaluate("""() => {
                      const rendered = el => !!el.getClientRects().length && getComputedStyle(el).display !== 'none' &&
                        getComputedStyle(el).visibility !== 'hidden';
                      const box = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}; };
                      const links = [...document.querySelectorAll('#tool-desk-tools-catalog a')].filter(rendered);
                      const search = document.querySelector('#tool-desk-search');
                      const filters = [...document.querySelectorAll('#tool-desk-directory-filters button')].filter(rendered);
                      const quickSteps = document.querySelector('.tool-desk-quick-steps');
                      const main = document.querySelector('#view-tool-desk-directory');
                      const controls = [...document.querySelectorAll('#view-tool-desk-directory button, #view-tool-desk-directory a, #view-tool-desk-directory input')].filter(rendered).map(el => ({
                        tag:el.tagName, label:(el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().slice(0,60), ...box(el)
                      }));
                      const tooSmall = controls.filter(c => c.w > 0 && c.h > 0 && (c.w < 24 || c.h < 24));
                      const clipped = controls.filter(c => c.right > 0 && c.x < innerWidth &&
                        (c.x < -1 || c.right > innerWidth + 1));
                      return {viewport:innerWidth,docWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,
                        title:document.title,toolLinks:links.length,search:search && rendered(search) ? box(search) : null,
                        filterCount:filters.length,filterBounds:filters.map(box),quickStepsVisible:quickSteps ? rendered(quickSteps) : null,mainBounds:box(main),
                        tooSmall:tooSmall.slice(0,12),clipped:clipped.slice(0,12),
                        firstCard:links[0] ? box(links[0]) : null,lastCard:links.at(-1) ? box(links.at(-1)) : null};
                    }""")
                    record = {"viewport": width, "http": response.status if response else None, **sample}
                    records.append(record)
                    if record["http"] != 200 or record["docWidth"] > width + 2 or record["toolLinks"] != 42:
                        errors.append(f"layout/catalog assertion: {record}")
                    if (width <= 600 and sample["quickStepsVisible"]) or (width > 600 and not sample["quickStepsVisible"]):
                        errors.append(f"responsive quick-steps visibility at {width}px: {sample['quickStepsVisible']}")
                    if sample["clipped"]:
                        errors.append(f"controls clipped at {width}px: {sample['clipped']}")
                    page.screenshot(path=str(OUT / f"homepage-responsive-{width}.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except Exception:
                app.kill()
    result = {"local_current_source": True, "route": "/", "viewports": records, "errors": errors}
    (OUT / "homepage-responsive-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"results": [{"viewport": r["viewport"], "http": r["http"], "docWidth": r["docWidth"],
                                    "toolLinks": r["toolLinks"], "filterCount": r["filterCount"],
                                    "clipped": len(r["clipped"]), "tooSmall": len(r["tooSmall"])} for r in records],
                      "errors": errors}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
