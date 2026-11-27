"""Check that the Hardened Redaction modal offers one clear primary action."""
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
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-redaction-action-") as temp:
        root = Path(temp)
        pdf = root / "security-action.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), "Redaction action button check. Test-only document.")
            doc.save(pdf)
        app, base, _ = helper.start_server(root / "data")
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base + "/protect-pdf", wait_until="domcontentloaded", timeout=20000)
                page.locator("#file-input").set_input_files(str(pdf))
                page.wait_for_timeout(500)
                page.locator("#open-security-audit-tool-btn").click()
                page.wait_for_function("document.querySelector('#security-modal')?.hidden === false")
                page.locator("#sec-tab-redact").click()
                page.wait_for_timeout(100)
                result = page.evaluate("""() => {
                  const actions = [...document.querySelectorAll('#security-modal button')]
                    .filter(button => button.textContent.includes('Execute Hardened Redaction'))
                    .filter(button => button.getClientRects().length && getComputedStyle(button).display !== 'none');
                  return {
                    count: actions.length,
                    labels: actions.map(button => button.textContent.trim()),
                    cancelVisible: !!document.querySelector('#btn-cancel-security')?.getClientRects().length,
                    paneActionCount: document.querySelectorAll('#sec-pane-redact button').length,
                    footerActionVisible: !!document.querySelector('#btn-apply-hardened-redact-footer')?.getClientRects().length
                  };
                }""")
                evidence["result_detail"] = result
                evidence["http_status"] = response.status if response else None
                browser.close()

            evidence["result"] = (
                evidence["http_status"] == 200 and result["count"] == 1
                and result["cancelVisible"] and result["paneActionCount"] == 0
                and result["footerActionVisible"]
                and not evidence["page_errors"] and not evidence["console_errors"]
            )
            output = ROOT / "reports" / "launch-audit-v24" / "browser-security-redaction-action.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()


if __name__ == "__main__":
    main()
