"""Current local Chromium visual/layout sweep for core mobile routes."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    output = Path(__file__).resolve().parent
    temp = TemporaryDirectory(prefix="paperplane-v23-mobile-visual-")
    app, base, _identities = helper.start_server(Path(temp.name) / "data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results, errors = [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width, height in ((320, 740), (390, 844), (820, 900)):
                page.set_viewport_size({"width": width, "height": height})
                for label, route in (("home", "/"), ("merge", "/merge-pdf"), ("pricing", "/pricing")):
                    response = page.goto(base + route, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(300)
                    if route == "/pricing":
                        page.locator("#pricing-limits-table tbody tr").first.wait_for(timeout=10000)
                        table_metrics = page.evaluate("""() => {
                          const region = document.querySelector('.pricing-limits-scroll');
                          const rows = [...document.querySelectorAll('#pricing-limits-table tbody tr')];
                          const regionRect = region.getBoundingClientRect();
                          return {regionWidth: region.clientWidth, regionScrollWidth: region.scrollWidth,
                            regionLeft: regionRect.left, regionRight: regionRect.right,
                            rowCount: rows.length, columns: rows.map(row => [...row.children].map(cell => ({
                              label: cell.dataset.label, text: cell.innerText.trim(),
                              renderedLabel: getComputedStyle(cell, '::before').content.replaceAll('"', ''),
                              left: cell.getBoundingClientRect().left, right: cell.getBoundingClientRect().right
                            })))};
                        }""")
                        if width <= 600:
                            assert table_metrics["rowCount"] == 44, table_metrics["rowCount"]
                            assert table_metrics["regionScrollWidth"] <= table_metrics["regionWidth"] + 1, table_metrics
                            assert all(len(row) == 5 and [cell["label"] for cell in row] ==
                                       ["Tool", "Batch", "File size", "Daily allowance", "Page limit"]
                                       and [cell["renderedLabel"] for cell in row] ==
                                       ["Tool", "Batch", "File size", "Daily allowance", "Page limit"]
                                       and all(cell["left"] >= table_metrics["regionLeft"] - 1 and
                                               cell["right"] <= table_metrics["regionRight"] + 1 for cell in row)
                                       for row in table_metrics["columns"]), "Mobile per-tool limits table has clipped columns"
                            page.locator("#pricing-limits-table tbody tr").first.screenshot(
                                path=str(output / "mobile-pricing-limits-row.png"))
                    else:
                        table_metrics = None
                    metrics = page.evaluate("""() => ({viewport: innerWidth,
                      documentWidth: document.documentElement.scrollWidth,
                      bodyWidth: document.body.scrollWidth,
                      main: (() => { const el=document.querySelector('main,#app-shell,#view-tool-desk-directory');
                        if (!el) return null; const r=el.getBoundingClientRect();
                        return {x:r.x,width:r.width,right:r.right}; })(),
                      title: document.title})""")
                    filename = f"mobile-{label}-{width}.png"
                    page.screenshot(path=str(output / filename), full_page=True)
                    row = {"route": route, "width": width, "status": response.status if response else None,
                           **metrics, "table_metrics": table_metrics, "screenshot": filename}
                    results.append(row)
                    assert row["status"] == 200 and row["documentWidth"] <= width + 2, row
            browser.close()
        result = {"checks": len(results), "failures": 0, "page_errors": errors, "routes": results}
        (output / "browser-mobile-visual.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        assert not errors, errors
    finally:
        app.terminate()
        app.wait(timeout=15)
        temp.cleanup()


if __name__ == "__main__":
    main()
