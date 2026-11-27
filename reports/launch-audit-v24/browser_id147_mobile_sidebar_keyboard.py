"""Verify the closed mobile navigation drawer cannot steal focus or pointer input."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id147-mobile-sidebar-keyboard.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id147-sidebar-") as temp_name:
        app, base, _ = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            result = {"viewport": {"width": 320, "height": 844}, "page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport=result["viewport"])
                page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
                page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#mobile-menu-btn").wait_for(state="visible")
                sidebar = page.locator("#sidebar")
                link = page.locator("#sidebar .nav-category-tab").first
                result["closed_state"] = sidebar.evaluate("e=>({inert:e.inert,ariaHidden:e.getAttribute('aria-hidden'),open:e.classList.contains('mobile-open')})")
                link.focus()
                result["closed_sidebar_control_cannot_receive_focus"] = page.evaluate("!document.querySelector('#sidebar .nav-category-tab').matches(':focus')")
                page.locator("#mobile-menu-btn").click()
                page.wait_for_function("document.querySelector('#sidebar')?.classList.contains('mobile-open') && document.querySelector('#sidebar').inert === false")
                result["open_state"] = sidebar.evaluate("e=>({inert:e.inert,ariaHidden:e.getAttribute('aria-hidden'),open:e.classList.contains('mobile-open')})")
                result["open_control_visible"] = link.is_visible()
                link.focus()
                result["open_sidebar_control_can_receive_focus"] = page.evaluate("document.querySelector('#sidebar .nav-category-tab').matches(':focus')")
                page.locator("#mobile-backdrop").click(position={"x": 315, "y": 200})
                page.wait_for_function("document.querySelector('#sidebar')?.inert === true")
                result["close_restores_focus_to_menu_toggle"] = page.evaluate("document.activeElement?.id === 'mobile-menu-btn'")
                result["closed_again"] = sidebar.evaluate("e=>({inert:e.inert,ariaHidden:e.getAttribute('aria-hidden'),open:e.classList.contains('mobile-open')})")
                browser.close()
            checks = [result["closed_state"] == {"inert": True, "ariaHidden": "true", "open": False}, result["closed_sidebar_control_cannot_receive_focus"], result["open_state"] == {"inert": False, "ariaHidden": "false", "open": True}, result["open_control_visible"], result["open_sidebar_control_can_receive_focus"], result["close_restores_focus_to_menu_toggle"], result["closed_again"] == {"inert": True, "ariaHidden": "true", "open": False}]
            result["result"] = "passed" if all(checks) and not result["page_errors"] and not result["console_errors"] else "failed"
            OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
            if result["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
