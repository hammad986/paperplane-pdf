"""Browser regression for stale tool guidance and SPA page titles (v24 ID 390)."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-route-title-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
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
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)

                page.goto(base + "/split-pdf", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_function("state.activeView === 'desk' && state.operation === 'split'")
                page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'split'")
                split = {"title": page.title(), "help_visible": page.locator(".seo-content").is_visible(),
                         "help_operation": page.locator(".seo-content").get_attribute("data-operation")}

                page.evaluate("switchWorkspaceView('ai')")
                page.wait_for_function("state.activeView === 'ai'")
                ai = {"title": page.title(), "help_visible": page.locator(".seo-content").is_visible()}

                page.go_back(wait_until="domcontentloaded")
                page.wait_for_function("state.activeView === 'desk' && state.operation === 'split'")
                page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'split'")
                back = {"title": page.title(), "help_visible": page.locator(".seo-content").is_visible(),
                        "help_operation": page.locator(".seo-content").get_attribute("data-operation")}

                page.go_forward(wait_until="domcontentloaded")
                page.wait_for_function("state.activeView === 'ai'")
                forward = {"title": page.title(), "help_visible": page.locator(".seo-content").is_visible()}
                browser.close()

            evidence["rounds"].append({"split": split, "ai": ai, "back": back, "forward": forward})
            evidence["result"] = (
                split["title"].startswith("Split / extract") and split["help_visible"] and split["help_operation"] == "split"
                and "AI Document Intelligence" in ai["title"] and not ai["help_visible"]
                and back["title"].startswith("Split / extract") and back["help_visible"] and back["help_operation"] == "split"
                and "AI Document Intelligence" in forward["title"] and not forward["help_visible"]
                and not evidence["page_errors"] and not evidence["console_errors"]
            )
            output = ROOT / "reports" / "launch-audit-v24" / "browser-route-help-title.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()


if __name__ == "__main__":
    main()
