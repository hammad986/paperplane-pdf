"""Browser test that compression preserves input text and does not grow the file."""
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
    source = ROOT / "web" / "assets" / "demo.pdf"
    with fitz.open(source) as document:
        original_text = "\n".join(page.get_text() for page in document)
        original_pages = len(document)
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-compression-size-") as temp:
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
                page = browser.new_page(viewport={"width": 390, "height": 844}, accept_downloads=True)
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base + "/compress-pdf", wait_until="domcontentloaded", timeout=20000)
                page.locator("#file-input").set_input_files(str(source))
                page.wait_for_function("state.files?.length === 1")
                page.locator("#run-button").click()
                page.wait_for_function("document.querySelector('#result-download-link') && !document.querySelector('#result-download-link').hidden", timeout=60000)
                with page.expect_download(timeout=30000) as download_info:
                    page.locator("#result-download-link").click()
                download = download_info.value
                output_path = Path(temp) / download.suggested_filename
                download.save_as(output_path)
                with fitz.open(output_path) as output:
                    output_text = "\n".join(p.get_text() for p in output)
                    output_pages = len(output)
                evidence.update({"http_status": response.status if response else None,
                                 "input_bytes": source.stat().st_size,
                                 "output_bytes": output_path.stat().st_size,
                                 "input_pages": original_pages, "output_pages": output_pages,
                                 "content_preserved": all(word in output_text for word in original_text.split() if len(word) > 2),
                                 "result_note": page.locator("#result-message").inner_text() if page.locator("#result-message").count() else ""})
                browser.close()

            evidence["result"] = (
                evidence["http_status"] == 200 and evidence["output_bytes"] <= evidence["input_bytes"]
                and evidence["output_pages"] == evidence["input_pages"] and evidence["content_preserved"]
                and not evidence["page_errors"] and not evidence["console_errors"]
            )
            output = ROOT / "reports" / "launch-audit-v24" / "browser-compression-smaller-output.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()


if __name__ == "__main__":
    main()
