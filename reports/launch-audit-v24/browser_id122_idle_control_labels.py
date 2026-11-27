from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id122-v239-idle-labels.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    with TemporaryDirectory(prefix="paperplane-id122-labels-") as tmp:
        app, base, _ = helper.start_server(Path(tmp) / "data")
        result = {"route": "/studio", "rounds": [], "page_errors": [], "unexpected_console_errors": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_number in (1, 2):
                    page = browser.new_page(viewport={"width": 390, "height": 844})
                    page.on("pageerror", lambda error: result["page_errors"].append(str(error).splitlines()[0][:220]))
                    page.on("console", lambda message: result["unexpected_console_errors"].append(message.text[:220]) if message.type == "error" else None)
                    response = page.goto(base + "/studio", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    before = page.evaluate("""() => ({
                      controls: document.querySelectorAll('input:not([type=hidden]), select, textarea').length,
                      missingNames: [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
                        .filter(control => !control.labels?.length && !control.getAttribute('aria-label') && !control.title).length
                    })""")
                    page.wait_for_function("""() => [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
                      .every(control => control.labels?.length || control.getAttribute('aria-label') || control.title)""", timeout=8000)
                    after = page.evaluate("""() => ({
                      controls: document.querySelectorAll('input:not([type=hidden]), select, textarea').length,
                      missingNames: [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
                        .filter(control => !control.labels?.length && !control.getAttribute('aria-label') && !control.title).length
                    })""")
                    page.evaluate("""() => {
                      const wrapper = document.createElement('div');
                      wrapper.id = 'idle-label-mutation-probe';
                      wrapper.innerHTML = '<input placeholder="Dynamically added label probe">';
                      document.body.append(wrapper);
                    }""")
                    page.wait_for_function("""() => {
                      const input = document.querySelector('#idle-label-mutation-probe input');
                      return Boolean(input?.labels?.length);
                    }""", timeout=3000)
                    dynamic = page.locator("#idle-label-mutation-probe input").evaluate("input => ({label: input.labels[0].textContent, id: input.id})")
                    assert after["missingNames"] == 0 and before["controls"] <= after["controls"], (before, after)
                    assert "Dynamically added label probe" in dynamic["label"], dynamic
                    result["rounds"].append({"round": round_number, "immediate": before, "eventually_named": after, "dynamic_mutation_label": dynamic})
                    page.close()
                browser.close()
            result["result"] = "passed" if len(result["rounds"]) == 2 and not result["page_errors"] and not result["unexpected_console_errors"] else "failed"
            OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
            if result["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=10)


if __name__ == "__main__":
    main()
