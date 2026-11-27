"""Verify the web-app install and native-app waitlist are clearly distinguished."""
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
    evidence: dict = {"viewports": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-native-waitlist-") as temp:
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
                for viewport in ((390, 844), (1366, 900)):
                    page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
                    page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                    page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                    response = page.goto(base + "/download", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_function("state.activeView === 'download'")
                    page.wait_for_timeout(250)
                    entry = page.evaluate("""() => ({
                      status: document.querySelector('#view-download h2')?.textContent.trim(),
                      badge: document.querySelector('#view-download .view-header-badge')?.textContent.trim(),
                      hero: document.querySelector('#view-download .download-hero-banner h3')?.textContent.trim(),
                      intro: document.querySelector('#view-download .download-hero-text p')?.textContent.trim(),
                      formTitle: document.querySelector('#waitlist-form')?.previousElementSibling?.querySelector('h4')?.textContent.trim(),
                      installText: document.querySelector('#install-app-btn')?.textContent.trim(),
                      installLabel: document.querySelector('#install-app-btn')?.getAttribute('aria-label'),
                      scrollWidth: document.documentElement.scrollWidth,
                      viewportWidth: innerWidth
                    })""")
                    entry["viewport"] = viewport
                    entry["http_status"] = response.status if response else None
                    evidence["viewports"].append(entry)
                    page.close()
                browser.close()

            evidence["result"] = all(
                entry["http_status"] == 200
                and entry["status"] == "Native Apps Early Access"
                and entry["badge"] == "Native installers coming later"
                and "install the web app" in entry["intro"].lower()
                and "native desktop and mobile installers" in entry["intro"].lower()
                and entry["formTitle"] == "Join the Native Apps Waitlist"
                and entry["installText"] == "Install Web App"
                and entry["installLabel"] == "Install Web App"
                and entry["scrollWidth"] == entry["viewportWidth"]
                for entry in evidence["viewports"]
            ) and not evidence["page_errors"] and not evidence["console_errors"]
            output = ROOT / "reports" / "launch-audit-v24" / "browser-native-app-waitlist.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()


if __name__ == "__main__":
    main()
