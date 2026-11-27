"""Check sidebar suite badges against the rendered Tool Desk category inventory."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id328-") as temp_name:
        app, base, _identity = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Local test server did not start")

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.wait_for_function("window.state?.operations && document.querySelectorAll('#tool-desk-tools-catalog .home-cat-section').length === 7", timeout=30000)

                categories = page.evaluate("""() => {
                  const nav = [...document.querySelectorAll('.nav-category-tab[data-category]')]
                    .filter(node => node.dataset.category !== 'All')
                    .map(node => ({key:node.dataset.category.toLowerCase(),label:node.querySelector('span:nth-child(2)')?.innerText,
                      count:Number(node.querySelector('.nav-cat-badge')?.innerText),aria:node.getAttribute('aria-label'),title:node.title}));
                  const grid = [...document.querySelectorAll('#tool-desk-tools-catalog .home-cat-section')].map(section => ({
                    key:section.dataset.cat,label:section.querySelector('.home-cat-title')?.innerText,
                    countLabel:section.querySelector('.home-cat-count')?.innerText.trim(),cards:section.querySelectorAll('.home-tool-card').length,
                    workspaceNote:section.querySelector('.tool-desk-ai-workspace-note')?.innerText || ''
                  }));
                  return {nav,grid,total:document.querySelector('#tool-desk-directory-filters [data-desk-category="all"]')?.innerText.trim()};
                }""")
                nav_by_key = {row["key"]: row for row in categories["nav"]}
                grid_by_key = {row["key"]: row for row in categories["grid"]}
                assert set(nav_by_key) == set(grid_by_key), categories
                represented_total = 0
                for key, sidebar in nav_by_key.items():
                    section = grid_by_key[key]
                    if key == "ai":
                        assert sidebar["count"] == 4, sidebar
                        assert sidebar["aria"] == "PDF Intelligence, 4 workflows", sidebar
                        assert section["countLabel"] == "1 tool + 3 in AI Intelligence", section
                        assert section["cards"] == 1 and section["workspaceNote"], section
                        assert all(word in section["workspaceNote"] for word in ("Chat", "Smart Metadata", "Executive Brief")), section
                        represented_total += section["cards"] + 3
                    else:
                        assert sidebar["count"] == section["cards"], {"sidebar": sidebar, "section": section}
                        assert section["countLabel"].startswith(str(section["cards"])), section
                        represented_total += section["cards"]
                assert represented_total == 44, {"represented_total": represented_total, "categories": categories}
                assert categories["total"] == "All 44 Tools", categories

                responsive = []
                for width in (320, 390, 820, 1366):
                    page.set_viewport_size({"width": width, "height": 900})
                    sizes = page.evaluate("""() => ({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
                      sidebarWidth:document.querySelector('.sidebar')?.getBoundingClientRect().width,
                      contentWidth:document.querySelector('#tool-desk-tools-catalog')?.getBoundingClientRect().width})""")
                    assert sizes["documentWidth"] <= width, sizes
                    responsive.append(sizes)
                evidence.update({"nav_counts": categories["nav"], "grid_counts": categories["grid"], "represented_total": represented_total,
                                "all_tools_label": categories["total"], "responsive": responsive})
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                page.screenshot(path=str(OUT / "browser-id328-category-count-parity.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id328-category-count-parity.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
