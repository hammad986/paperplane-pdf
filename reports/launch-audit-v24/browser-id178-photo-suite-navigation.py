"""Verify selecting Photo & Exam always opens matching Photo tool content."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id178-photo-suite-navigation.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id178-") as temp_name:
        app, base, _identities = helper.start_server(Path(temp_name) / "data")
        evidence = {"page_errors": [], "console_errors": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                page.locator("#view-ai-studio").wait_for(state="visible")
                page.locator('.nav-category-tab[data-category="Photo"]').click()
                page.locator("#view-tool-desk-directory").wait_for(state="visible")
                page.wait_for_function("document.querySelector('#tool-desk-tools-catalog .home-cat-section[data-cat=photo]') !== null")
                evidence["after_click"] = page.evaluate("""() => ({
                  active_view: state.activeView,
                  directory_visible: !document.querySelector('#view-tool-desk-directory').hidden,
                  ai_view_hidden: document.querySelector('#view-ai-studio').hidden,
                  selected_suite: document.querySelector('.nav-category-tab.active')?.dataset.category,
                  selected_filter: document.querySelector('#tool-desk-directory-filters .filter-pill.active')?.dataset.deskCategory,
                  sections: [...document.querySelectorAll('#tool-desk-tools-catalog .home-cat-section')].map(s => s.dataset.cat),
                  visible_tools: [...document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card .home-tool-title')].map(e => e.textContent.trim())
                })""")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and evidence.get("after_click", {}).get("active_view") == "tool-desk"
            and evidence.get("after_click", {}).get("directory_visible") is True
            and evidence.get("after_click", {}).get("ai_view_hidden") is True
            and evidence.get("after_click", {}).get("selected_suite") == "Photo"
            and evidence.get("after_click", {}).get("selected_filter") == "photo"
            and evidence.get("after_click", {}).get("sections") == ["photo"]
            and evidence.get("after_click", {}).get("visible_tools")
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
