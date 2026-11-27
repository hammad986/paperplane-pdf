"""Verify Studio page labels stay inside organizer tiles at narrow widths."""
import json
import os
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROUND = os.getenv("PAPERPLANE_ID216_ROUND", "1")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    evidence = {"checks": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-id216-v228-") as td:
        temp = Path(td)
        fixture = temp / "organizer-12-pages.pdf"
        with fitz.open() as document:
            for number in range(1, 13):
                page = document.new_page()
                page.insert_text((72, 72), f"Organizer label fixture page {number}")
            document.save(fixture)
        app, base, _ = helper.start_server(temp / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on(
                    "console",
                    lambda message: evidence["console_errors"].append(message.text)
                    if message.type == "error" else None,
                )
                response = page.goto(base + "/", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.evaluate("switchWorkspaceView('studio')")
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function(
                    "document.querySelectorAll('.organizer-thumb-card').length === 12",
                    timeout=30000,
                )
                page.evaluate("document.querySelector('#app-shell').classList.add('studio-pages-open')")
                page.wait_for_timeout(300)
                if page.locator("#org-grid-view-btn").count():
                    page.locator("#org-grid-view-btn").click(force=True)
                page.wait_for_timeout(400)

                for width, height in ((320, 844), (390, 844), (820, 900), (1366, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(200)
                    metrics = page.evaluate(
                        """() => {
                          const rect = element => {
                            const r = element.getBoundingClientRect();
                            return {left:r.left, top:r.top, right:r.right, bottom:r.bottom,
                              width:r.width, height:r.height};
                          };
                          const cards = [...document.querySelectorAll('.organizer-thumb-card')]
                            .filter(card => card.getBoundingClientRect().width > 0);
                          const labels = cards.map(card => {
                            const label = card.querySelector('.thumb-page-num');
                            const c = rect(card), l = rect(label);
                            return {page:card.dataset.page, text:label.textContent.trim(),
                              card:c, label:l, whiteSpace:getComputedStyle(label).whiteSpace,
                              insideCard:l.left >= c.left - 1 && l.right <= c.right + 1 &&
                                l.top >= c.top - 1 && l.bottom <= c.bottom + 1};
                          });
                          return {width:innerWidth, documentWidth:document.documentElement.scrollWidth,
                            totalCards:document.querySelectorAll('.organizer-thumb-card').length,
                            visibleCards:cards.length, labels};
                        }"""
                    )
                    metrics["passed"] = (
                        metrics["documentWidth"] <= width
                        and metrics["totalCards"] == 12
                        and metrics["visibleCards"] == 12
                        and all(label["insideCard"] and label["whiteSpace"] == "nowrap"
                                and label["text"] == label["page"] for label in metrics["labels"])
                    )
                    evidence["checks"].append(metrics)
                    page.screenshot(path=str(OUT / f"browser-v228-id216-{width}-round-{ROUND}.png"))
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["round"] = ROUND
    evidence["passed"] = (
        len(evidence["checks"]) == 4
        and all(check["passed"] for check in evidence["checks"])
        and not evidence["page_errors"]
        and not evidence["console_errors"]
    )
    (OUT / f"browser-v228-id216-organizer-labels-round-{ROUND}.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "round": ROUND,
        "widths": [check["width"] for check in evidence["checks"]],
        "visible_cards": [check["visibleCards"] for check in evidence["checks"]],
        "labels_inside_cards": all(
            label["insideCard"] for check in evidence["checks"] for label in check["labels"]
        ),
        "browser_errors": evidence["page_errors"] + evidence["console_errors"],
        "passed": evidence["passed"],
    }, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
