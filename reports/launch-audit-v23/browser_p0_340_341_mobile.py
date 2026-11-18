"""Recheck fixed mobile actions and narrow AI Intelligence location label."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"action_checks": [], "breadcrumb_checks": [], "page_errors": []}
    with TemporaryDirectory(prefix="paperplane-v23-mobile-actions-") as temp:
        temp_path = Path(temp)
        source_pdf = temp_path / "mobile-action-check.pdf"
        with fitz.open() as document:
            page = document.new_page(width=300, height=200)
            page.insert_text((40, 70), "MOBILE ACTION BUTTON CHECK", fontsize=12)
            second_page = document.new_page(width=300, height=200)
            second_page.insert_text((40, 70), "SECOND PAGE", fontsize=12)
            document.save(source_pdf)
        second_pdf = temp_path / "mobile-action-check-2.pdf"
        with fitz.open() as document:
            document.new_page(width=300, height=200).insert_text((40, 70), "SECOND SOURCE", fontsize=12)
            document.save(second_pdf)
        app, base, _identities = helper.start_server(temp_path / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane test server did not start.")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for width, height in ((320, 780), (390, 844), (820, 900)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                    for slug in ("merge-pdf", "split-pdf", "compress-pdf"):
                        response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=20000)
                        action = page.locator("#run-button")
                        action.wait_for(state="visible", timeout=10000)
                        page.locator("#file-input").set_input_files(
                            [str(source_pdf), str(second_pdf)] if slug == "merge-pdf" else str(source_pdf)
                        )
                        if slug == "split-pdf":
                            page.locator("#split_mode").select_option("all_pages", timeout=10000)
                        page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=10000)
                        action.scroll_into_view_if_needed()
                        page.wait_for_timeout(100)
                        geometry = page.evaluate("""() => {
                          const action = document.querySelector('#run-button');
                          const nav = document.querySelector('.mobile-workspace-bar');
                          const a = action.getBoundingClientRect();
                          const n = nav.getBoundingClientRect();
                          const center = document.elementFromPoint(a.left + a.width / 2, a.top + a.height / 2);
                          return {
                            viewport: innerWidth,
                            documentWidth: document.documentElement.scrollWidth,
                            action: {left: a.left, right: a.right, top: a.top, bottom: a.bottom},
                            nav: {top: n.top, bottom: n.bottom, display: getComputedStyle(nav).display},
                            overlapsNav: a.left < n.right && a.right > n.left && a.top < n.bottom && a.bottom > n.top,
                            centerCoveredByNav: !!center?.closest('.mobile-workspace-bar'),
                            centerTag: center?.tagName,
                            enabled: !action.disabled
                          };
                        }""")
                        row = {"width": width, "height": height, "operation": slug,
                               "http_status": response.status if response else None, **geometry}
                        evidence["action_checks"].append(row)
                        if slug == "split-pdf":
                            page.screenshot(path=str(ROOT / "reports" / "launch-audit-v23" / f"p0-340-split-{width}.png"), full_page=True)

                    response = page.goto(f"{base}/ai-intelligence", wait_until="domcontentloaded", timeout=20000)
                    label = page.locator("#mobile-view-pill").inner_text().strip()
                    crumb = page.evaluate("""() => ({
                      display: getComputedStyle(document.querySelector('.breadcrumb-trail')).display,
                      width: document.querySelector('.breadcrumb-trail').getBoundingClientRect().width,
                      text: document.querySelector('.breadcrumb-trail').innerText.trim(),
                      viewport: innerWidth,
                      documentWidth: document.documentElement.scrollWidth
                    })""")
                    evidence["breadcrumb_checks"].append({"viewportWidth": width, "http_status": response.status if response else None,
                                                          "mobile_label": label, **crumb})
                    page.screenshot(path=str(ROOT / "reports" / "launch-audit-v23" / f"p0-341-ai-{width}.png"), full_page=True)
                    page.close()
                browser.close()

            evidence["action_failures"] = [row for row in evidence["action_checks"]
                                          if row["http_status"] != 200 or row["documentWidth"] > row["width"]
                                          or row["overlapsNav"] or row["centerCoveredByNav"]
                                          or row["centerTag"] != "BUTTON"]
            evidence["breadcrumb_failures"] = [row for row in evidence["breadcrumb_checks"]
                                              if row["http_status"] != 200 or row["documentWidth"] > row["viewportWidth"]
                                              or row["display"] != "none" or row["mobile_label"] != "AI Intelligence"]
            evidence["result"] = not evidence["action_failures"] and not evidence["breadcrumb_failures"] and not evidence["page_errors"]
            output = ROOT / "reports" / "launch-audit-v23" / "browser-p0-340-341-mobile-layout.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()
            try:
                app.wait(timeout=8)
            except Exception:
                app.kill()


if __name__ == "__main__":
    main()
