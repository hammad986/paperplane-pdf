"""Browser test for visible warnings on formula cells without cached results."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import openpyxl
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-uncached-formula-") as temp:
        root = Path(temp)
        workbook_path = root / "uncached-budget.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Budget"
        sheet.append(["Item", "Amount"])
        sheet.append(["Rent", 1200])
        sheet.append(["Total", "=SUM(B2:B2)"])
        workbook.save(workbook_path)

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
                page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base + "/excel-to-pdf", wait_until="domcontentloaded", timeout=20000)
                page.locator("#file-input").set_input_files(str(workbook_path))
                page.wait_for_function("state.files?.length === 1")
                page.locator("#run-button").click()
                page.wait_for_function("document.querySelector('#result-download-link') && !document.querySelector('#result-download-link').hidden", timeout=60000)
                link = page.locator("#result-download-link")
                with page.expect_download(timeout=30000) as download_info:
                    link.click()
                download = download_info.value
                pdf_path = root / download.suggested_filename
                download.save_as(pdf_path)
                with fitz.open(pdf_path) as pdf:
                    output_text = "\n".join(sheet.get_text() for sheet in pdf)
                    pages = len(pdf)
                evidence.update({"http_status": response.status if response else None,
                                 "download_name": download.suggested_filename,
                                 "download_bytes": pdf_path.stat().st_size,
                                 "pages": pages, "output_text": output_text})
                browser.close()

            evidence["result"] = (
                evidence["http_status"] == 200 and evidence["download_bytes"] > 0
                and "Formula result unavailable" in evidence["output_text"]
                and "=SUM(B2:B2)" in evidence["output_text"]
                and "Rent" in evidence["output_text"] and not evidence["page_errors"]
                and not evidence["console_errors"]
            )
            output = ROOT / "reports" / "launch-audit-v24" / "browser-uncached-excel-formula.json"
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            app.terminate()


if __name__ == "__main__":
    main()
