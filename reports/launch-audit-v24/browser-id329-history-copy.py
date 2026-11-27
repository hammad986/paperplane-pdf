"""Verify the History page plainly explains its temporary, non-retained results."""
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
    with TemporaryDirectory(prefix="paperplane-v24-id329-") as temp_name:
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/history", wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('main')?.innerText.includes('job or download history list')", timeout=15000)
                paragraph = page.locator("main").inner_text()
                assert "Paperplane does not keep a job or download history list." in paragraph, paragraph
                assert "browser results are tied to the current tab" in paragraph.lower(), paragraph
                assert "server download links expire automatically" in paragraph.lower(), paragraph
                assert page.locator("main").inner_text().lower().count("temporary results") >= 1, paragraph
                widths = []
                for width in (320, 390, 820, 1366):
                    page.set_viewport_size({"width": width, "height": 844})
                    metric = page.evaluate("""() => ({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
                      mainWidth:document.querySelector('main')?.getBoundingClientRect().width})""")
                    assert metric["documentWidth"] <= width, metric
                    widths.append(metric)
                evidence.update({"history_copy": paragraph, "responsive": widths})
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                page.screenshot(path=str(OUT / "browser-id329-history-copy-390.png"), full_page=True)
                page.set_viewport_size({"width": 1366, "height": 900})
                page.screenshot(path=str(OUT / "browser-id329-history-copy-1366.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id329-history-copy.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
