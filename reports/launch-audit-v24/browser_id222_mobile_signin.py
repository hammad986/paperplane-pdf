"""Verify direct guest sign-in remains discoverable and usable on small phones."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id222-mobile-signin.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    widths = [320, 360, 390, 480]
    with TemporaryDirectory(prefix="paperplane-id222-mobile-signin-") as temp_name:
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
            evidence = {"widths": widths, "checks": [], "page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 320, "height": 844})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.locator("#topbar-signin-btn").wait_for(state="attached")
                page.wait_for_timeout(250)
                for width in widths:
                    page.set_viewport_size({"width": width, "height": 844})
                    page.wait_for_timeout(100)
                    check = page.evaluate("""() => {
                      const login=document.querySelector('#topbar-signin-btn'), register=document.querySelector('#topbar-register-btn');
                      const r=login.getBoundingClientRect();
                      return {width:innerWidth,loginVisible:!!(r.width&&r.height&&getComputedStyle(login).visibility==='visible'),loginInBounds:r.left>=0&&r.right<=innerWidth,registerHidden:!register.getClientRects().length,topbarRightDisplay:getComputedStyle(document.querySelector('.topbar-right')).display,documentWidth:document.documentElement.scrollWidth};
                    }""")
                    check["result"] = "passed" if check["loginVisible"] and check["loginInBounds"] and check["registerHidden"] and check["documentWidth"] <= width + 2 else "failed"
                    evidence["checks"].append(check)
                page.set_viewport_size({"width": 320, "height": 844})
                page.locator("#topbar-signin-btn").click()
                evidence["login_dialog_opens"] = page.locator("#auth-modal").is_visible() and page.locator("#tab-login").get_attribute("class").find("active") >= 0
                page.locator("#tab-register").click()
                evidence["registration_available_from_dialog"] = page.locator("#tab-register").get_attribute("class").find("active") >= 0
                evidence["auth_dialog_fits_viewport"] = page.evaluate("""() => {const r=document.querySelector('#auth-modal .modal-card')?.getBoundingClientRect();return !!r&&r.left>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}""")
                browser.close()
            evidence["result"] = "passed" if all(x["result"] == "passed" for x in evidence["checks"]) and evidence["login_dialog_opens"] and evidence["registration_available_from_dialog"] and evidence["auth_dialog_fits_viewport"] and not evidence["page_errors"] and not evidence["console_errors"] else "failed"
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if evidence["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
