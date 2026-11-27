"""Compare the Settings billing pane through modal and dedicated route entry."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id160-settings-entrypoint-parity.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id160-") as temp_name:
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
                response = page.goto(base + "/", wait_until="domcontentloaded")
                page.locator("#sidebar-settings-gear-btn").click()
                page.locator("#settings-modal:not([hidden])").wait_for()
                page.locator("#settings-tab-btn-billing").click()
                page.locator("#pane-billing:not([hidden])").wait_for()
                evidence["modal"] = page.locator("#pane-billing").inner_text()
                evidence["modal_visible_controls"] = page.locator("#pane-billing button:visible").all_inner_texts()
                page.locator("#close-settings-modal").click()
                page.goto(base + "/settings", wait_until="domcontentloaded")
                page.locator("#settings-modal.workspace-inline-panel:not([hidden])").wait_for()
                page.locator("#settings-tab-btn-billing").click()
                page.locator("#pane-billing:not([hidden])").wait_for()
                evidence["dedicated_route"] = page.locator("#pane-billing").inner_text()
                evidence["dedicated_visible_controls"] = page.locator("#pane-billing button:visible").all_inner_texts()
                evidence["same_panel_instance"] = page.locator("#settings-modal").evaluate("el => el.parentElement.id === 'settings-page-content'")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and evidence.get("modal") == evidence.get("dedicated_route")
            and evidence.get("modal_visible_controls") == evidence.get("dedicated_visible_controls")
            and evidence.get("same_panel_instance") is True
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({"overall": evidence["overall"], "http_status": evidence.get("http_status"),
                          "pane_text_equal": evidence.get("modal") == evidence.get("dedicated_route"),
                          "visible_controls_equal": evidence.get("modal_visible_controls") == evidence.get("dedicated_visible_controls"),
                          "same_panel_instance": evidence.get("same_panel_instance"),
                          "controls": evidence.get("modal_visible_controls"),
                          "page_errors": evidence["page_errors"], "console_errors": evidence["console_errors"]}, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
