"""Check home, tool, and Apps waitlist how-to cards have useful body text."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id172-howto-guidance-content.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

ROUTES = ("/tool-desk", "/ocr-pdf", "/translate-pdf", "/html-to-pdf", "/jpg-to-pdf")


def main():
    with TemporaryDirectory(prefix="paperplane-id172-") as temp_name:
        app, base, _identities = helper.start_server(Path(temp_name) / "data")
        evidence = {"page_errors": [], "console_errors": [], "routes": {}}
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
                for route in ROUTES:
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    if route == "/tool-desk":
                        selector = ".tool-desk-quick-steps .seo-howto-step"
                    else:
                        selector = ".seo-content .seo-howto-step"
                        page.wait_for_function("document.querySelectorAll('.seo-content .seo-howto-step').length >= 2")
                    cards = page.locator(selector)
                    evidence["routes"][route] = {
                        "http_status": response.status if response else None,
                        "steps": cards.evaluate_all("els => els.map(el => ({heading:el.querySelector('h3')?.textContent.trim(), body:el.querySelector('p')?.textContent.trim()}))"),
                        "visible_controls_preupload": page.evaluate("""() => [...document.querySelectorAll('#options input, #options select, #options textarea, #options button, #ocr-language-select, #target_language, #url')]
                          .filter(el => {const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 && getComputedStyle(el).visibility!=='hidden' && !el.disabled;})
                          .map(el => ({id:el.id, tag:el.tagName, label:el.labels?.[0]?.textContent.trim() || el.getAttribute('aria-label') || el.placeholder || ''}))""")
                    }
                page.evaluate("() => switchWorkspaceView('download', 'privacy', false)")
                download_cards = page.locator("#view-download .download-howto-section .seo-howto-step")
                evidence["download_view"] = download_cards.evaluate_all("els => els.map(el => ({heading:el.querySelector('h3')?.textContent.trim(), body:el.querySelector('p')?.textContent.trim()}))")
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)
        bodies_ok = all(
            len(route_data["steps"]) >= 2 and all(step["heading"] and step["body"] for step in route_data["steps"])
            for route_data in evidence["routes"].values()
        )
        download_specific = len(evidence.get("download_view", [])) == 3 and all(
            step["body"] for step in evidence["download_view"]
        ) and any("waitlist" in step["body"].lower() or "installer" in step["body"].lower() for step in evidence["download_view"])
        evidence["overall"] = "passed" if (
            bodies_ok and download_specific
            and all(route_data["http_status"] == 200 for route_data in evidence["routes"].values())
            and "target_language" in {control["id"] for control in evidence["routes"]["/translate-pdf"]["visible_controls_preupload"]}
            and "url" in {control["id"] for control in evidence["routes"]["/html-to-pdf"]["visible_controls_preupload"]}
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({"overall": evidence["overall"], "routes": evidence["routes"],
                          "download_view": evidence.get("download_view"),
                          "page_errors": evidence["page_errors"], "console_errors": evidence["console_errors"]}, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
