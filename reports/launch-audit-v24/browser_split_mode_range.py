"""Verify Split disables range entry in all-pages mode and exports exact ranges."""
from __future__ import annotations

import io
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
    with TemporaryDirectory(prefix="paperplane-v24-split-mode-") as temp_name:
        temp = Path(temp_name)
        source = temp / "ten-distinct-pages.pdf"
        with fitz.open() as pdf:
            for page_number in range(1, 11):
                pdf.new_page().insert_text((72, 72), f"SPLIT FIXTURE PAGE {page_number}")
            pdf.save(source)

        app, base, _ = helper.start_server(temp / "data")
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
                page = browser.new_page(accept_downloads=True, viewport={"width": 1100, "height": 850})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                        if message.type == "error" else None)
                requests = []
                page.on("request", lambda request: requests.append(request.url))
                page.goto(base + "/split-pdf", wait_until="domcontentloaded")
                page.wait_for_function("state.operation === 'split'")
                page.locator("#client-privacy-toggle").check()
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#split_mode").wait_for(state="visible", timeout=10000)
                page.wait_for_function("document.querySelector('#split_mode option[value=all_pages]')")
                page.select_option("#split_mode", "all_pages")
                all_pages_state = page.evaluate("""() => ({
                  mode: document.querySelector('#split_mode').value,
                  rangeHidden: document.querySelector('#split-range-container').hidden,
                  rangeDisabled: document.querySelector('#pages').disabled,
                  help: document.querySelector('#split-mode-help').textContent.trim()
                })""")
                assert all_pages_state["mode"] == "all_pages"
                assert all_pages_state["rangeHidden"] and all_pages_state["rangeDisabled"]
                assert "all pages" in all_pages_state["help"].lower()

                page.select_option("#split_mode", "range")
                range_input = page.locator("#pages")
                assert range_input.is_visible() and range_input.is_enabled()
                range_input.fill("11")
                page.locator("#run-button").click()
                page.wait_for_timeout(100)
                invalid_state = page.evaluate("""() => ({
                  value: document.querySelector('#pages').value,
                  focused: document.activeElement === document.querySelector('#pages'),
                  invalid: document.querySelector('#pages').getAttribute('aria-invalid'),
                  help: document.querySelector('#split-mode-help').textContent.trim(),
                  uploadPromptShown: Boolean(document.querySelector('.app-confirm-dialog'))
                })""")
                assert invalid_state["value"] == "11" and invalid_state["focused"]
                assert invalid_state["invalid"] == "true" and "1 to 10" in invalid_state["help"]
                assert not invalid_state["uploadPromptShown"]
                assert not any("/api/jobs" in url for url in requests), requests

                range_input.fill("2-3")
                page.locator("#run-button").click()
                page.wait_for_function("!document.querySelector('#result').hidden", timeout=30000)
                with page.expect_download(timeout=30000) as download_info:
                    page.locator("#result-download-link").click()
                download = download_info.value
                output_path = temp / download.suggested_filename
                download.save_as(str(output_path))
                with fitz.open(output_path) as output_pdf:
                    found = [document_page.get_text().strip() for document_page in output_pdf]
                assert len(found) == 2 and "PAGE 2" in found[0] and "PAGE 3" in found[1], found
                evidence["rounds"].append({
                    "all_pages_mode": all_pages_state,
                    "invalid_range_inline_validation": invalid_state,
                    "custom_mode_range_enabled": range_input.is_enabled(),
                    "custom_range": "2-3",
                    "download_name": download.suggested_filename,
                    "output_page_count": len(found),
                    "page_text": found,
                    "output_content_checked": True,
                })
                evidence["result"] = True
                browser.close()
        finally:
            app.terminate()

    evidence["result"] = evidence.get("result", False) and not evidence["page_errors"] and not evidence["console_errors"]
    output = ROOT / "reports" / "launch-audit-v24" / "browser-split-mode-range.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["result"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
