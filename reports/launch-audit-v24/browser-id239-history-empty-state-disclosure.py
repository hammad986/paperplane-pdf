"""Check that the no-history page and footer label clearly say history is not kept."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id239-history-empty-state-disclosure.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id239-") as temp_name:
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
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/history", wait_until="domcontentloaded")
                page.locator("#view-history").wait_for(state="visible")
                evidence["page"] = page.locator("#view-history").inner_text()
                footer_link = page.locator('.app-global-footer a[href="/history"]')
                page.wait_for_function("document.documentElement.classList.contains('footer-revealed')")
                evidence["scroll_metrics"] = page.evaluate("""() => {
                  const main=document.querySelector('.main-area');
                  const footer=document.querySelector('.app-global-footer');
                  const rect=footer.getBoundingClientRect();
                  return {revealed:document.documentElement.classList.contains('footer-revealed'), main_scroll_top:main.scrollTop,
                    main_scroll_height:main.scrollHeight, main_client_height:main.clientHeight,
                    page_scroll_y:scrollY, page_scroll_height:document.documentElement.scrollHeight,
                    viewport_height:innerHeight, footer_top:rect.top, footer_bottom:rect.bottom,
                    footer_visibility:getComputedStyle(footer).visibility};
                }""")
                evidence["footer_history_label"] = footer_link.inner_text()
                evidence["history_list_or_placeholder"] = page.locator("#view-history").evaluate("el => ({hasList:!!el.querySelector('table, [role=\"list\"], .history-list'), hasHeading:!!el.querySelector('h1')})")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and evidence.get("scroll_metrics", {}).get("revealed") is True
            and "Temporary results" in evidence.get("page", "")
            and "no saved history" in evidence.get("page", "").lower()
            and "does not keep a job or download history list" in evidence.get("page", "")
            and "Temporary results" in evidence.get("footer_history_label", "")
            and evidence.get("history_list_or_placeholder", {}).get("hasList") is False
            and evidence.get("history_list_or_placeholder", {}).get("hasHeading") is True
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
