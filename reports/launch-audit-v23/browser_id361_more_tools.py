"""Content and geometry checks for the Studio More Tools overflow menu."""
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
    with TemporaryDirectory(prefix="paperplane-id361-") as temp:
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
                for width, height in ((1366, 900), (820, 900), (390, 844)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                    page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                    response = page.goto(base, wait_until="domcontentloaded", timeout=20000)
                    studio_nav = page.locator("#tab-studio-view") if width > 900 else page.locator("#mob-nav-studio")
                    studio_nav.click()
                    trigger = page.locator("#btn-more-tools-trigger")
                    trigger.wait_for(state="visible", timeout=10000)
                    trigger.click()
                    menu = page.locator("#studio-more-dropdown")
                    page.wait_for_function("document.querySelector('#studio-more-dropdown')?.hidden === false")
                    first = page.locator("#studio-more-dropdown .studio-dropdown-item").first
                    first.focus()
                    geometry = menu.evaluate("""el => {
                      const r = el.getBoundingClientRect();
                      return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,
                        scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,position:getComputedStyle(el).position,
                        parent:el.parentElement?.tagName};
                    }""")
                    labels = page.locator("#studio-more-dropdown .studio-dropdown-item span").all_text_contents()
                    page.locator("#studio-more-dropdown").evaluate("el => { el.scrollTop = el.scrollHeight; }")
                    last = page.locator("#studio-security-btn")
                    last.scroll_into_view_if_needed()
                    final_state = page.evaluate("""() => {
                      const menu = document.querySelector('#studio-more-dropdown');
                      const last = document.querySelector('#studio-security-btn').getBoundingClientRect();
                      return {scrollTop:menu.scrollTop,lastBottom:last.bottom,viewportHeight:innerHeight,
                        lastVisible:last.bottom <= innerHeight && last.top >= 0,
                        expanded:document.querySelector('#btn-more-tools-trigger').getAttribute('aria-expanded')};
                    }""")
                    page.screenshot(path=str(ROOT / "reports" / "launch-audit-v23" / f"id361-more-tools-{width}.png"))
                    page.keyboard.press("Escape")
                    closed = menu.is_hidden()
                    focus_restored = trigger.evaluate("el => document.activeElement === el")
                    evidence["rounds"].append({"viewport": [width, height], "http_status": response.status if response else None,
                                              "geometry": geometry, "labels": labels, "final_state": final_state,
                                              "closed_on_escape": closed, "focus_restored": focus_restored})
                    page.close()
                browser.close()

            failures = []
            expected = ["Compress PDF", "OCR Searchable PDF", "Repair Corrupted PDF", "Convert to / from PDF",
                        "Form Fields & Fill", "Digital Signatures", "Protect & Unlock PDF"]
            for round_result in evidence["rounds"]:
                g = round_result["geometry"]
                f = round_result["final_state"]
                if (round_result["http_status"] != 200 or round_result["labels"] != expected
                    or g["position"] != "fixed" or g["left"] < 0 or g["right"] > round_result["viewport"][0]
                    or g["top"] < 0 or g["bottom"] > round_result["viewport"][1]
                    or (g["scrollHeight"] > g["clientHeight"] + 2 and f["scrollTop"] <= 0)
                    or not f["lastVisible"] or f["expanded"] != "true"
                    or not round_result["closed_on_escape"] or not round_result["focus_restored"]):
                    failures.append(round_result)
            evidence["failures"] = failures
            evidence["result"] = not failures and not evidence["page_errors"] and not evidence["console_errors"]
            output = ROOT / "reports" / "launch-audit-v23" / "browser-id361-more-tools.json"
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
