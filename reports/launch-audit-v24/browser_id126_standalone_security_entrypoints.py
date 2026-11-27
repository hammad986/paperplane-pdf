"""Verify the standalone Protect/Unlock pages can open Security Audit & Sanitize."""
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
OUT = ROOT / "reports/launch-audit-v24/browser-id126-standalone-security-entrypoints.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id126-") as temp_name:
        temp = Path(temp_name)
        source = temp / "security-entrypoint.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Standalone security audit entrypoint check")
            document.save(source)
        app, base, _ = helper.start_server(temp / "data")
        try:
            parsed_port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", parsed_port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            checks = []
            page_errors, console_errors = [], []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                for route in ("/protect-pdf", "/unlock-pdf"):
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    assert response and response.status == 200, route
                    app_src = page.locator('script[src*="/assets/app.js"]').get_attribute("src")
                    assert app_src == "/assets/app.js?v=206", app_src
                    page.locator("#file-input").set_input_files(str(source))
                    entrypoint = page.locator("#open-security-audit-tool-btn")
                    entrypoint.wait_for(state="visible", timeout=15000)
                    entrypoint.click()
                    page.wait_for_function("!document.querySelector('#security-modal').hidden", timeout=10000)
                    audit_visible = page.locator("#sec-pane-audit").evaluate("element => getComputedStyle(element).display !== 'none'")
                    report_container = page.locator("#sec-audit-report").count() == 1
                    sanitize_button_count = page.locator("#btn-apply-sanitize").count()
                    assert audit_visible and report_container and sanitize_button_count == 1, route
                    checks.append({
                        "route": route,
                        "http_status": response.status,
                        "app_src": app_src,
                        "modal_visible": True,
                        "audit_pane_visible": audit_visible,
                        "sanitize_button_count": sanitize_button_count,
                        "uploaded_filename": source.name,
                    })
                    page.locator("#modal-close-security").click()
                assert not page_errors and not console_errors, (page_errors, console_errors)
                browser.close()

            evidence = {
                "viewport": {"width": 390, "height": 844},
                "checks": checks,
                "page_errors": page_errors,
                "console_errors": console_errors,
                "result": "passed",
            }
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
