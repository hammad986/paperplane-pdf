from __future__ import annotations

import json
import socket
import sys
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id156-") as temp:
        work = Path(temp)
        source = work / "split-mode-four-page.pdf"
        with fitz.open() as document:
            for number in range(1, 5):
                page = document.new_page(width=595, height=842)
                page.insert_text((72, 72), f"Split output page marker {number}.")
            document.save(source)
        app, base, _ = helper.start_server(work / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(accept_downloads=True, viewport={"width": 1365, "height": 900}, service_workers="block")
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for round_no in (1, 2):
                    response = page.goto(f"{base}/split-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#split_mode").wait_for(state="visible")
                    assert "ZIP" in page.locator("#split_mode").locator("option[value='all_pages']").inner_text()
                    page.locator("#split_mode").select_option("all_pages")
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                    with page.expect_download(timeout=15000) as event:
                        page.locator("#result-download-link").click()
                    output = work / f"split-round-{round_no}.zip"
                    event.value.save_as(output)
                    with zipfile.ZipFile(output) as archive:
                        names = archive.namelist()
                        assert len(names) == 4 and all(name.lower().endswith(".pdf") for name in names), names
                        markers = []
                        for name in names:
                            with fitz.open(stream=archive.read(name), filetype="pdf") as pdf:
                                assert pdf.page_count == 1
                                markers.append(pdf[0].get_text().strip())
                    assert sorted(markers) == [f"Split output page marker {n}." for n in range(1, 5)], markers
                    evidence["rounds"].append({"round": round_no, "mode": "all_pages", "archive_members": names,
                        "content_checked_one_page_pdfs": len(markers), "source_markers_preserved": True,
                        "output_media": "application/zip"})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 2 and not evidence["page_errors"] and not evidence["console_errors"]
    output_path = ROOT / "reports" / "launch-audit-v24" / "browser-id156-split-zip-output.json"
    output_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
