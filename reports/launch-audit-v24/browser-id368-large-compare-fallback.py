"""Exercise large Compare PDFs in local Chrome and content-check server fallback."""
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
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def build_fixture(path: Path, label: str) -> int:
    lines_per_page = 30
    with fitz.open() as pdf:
        for page_no in range(1, 70):
            page = pdf.new_page()
            for line_no in range(1, lines_per_page + 1):
                line = f"{label}-PAGE-{page_no:02d}-LINE-{line_no:03d} UNIQUE DETAIL"
                page.insert_text((30, 30 + line_no * 11), line, fontsize=7)
        pdf.save(path)
    return 69 * lines_per_page


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id368-") as temp_name:
        temp = Path(temp_name)
        left = temp / "left-69-page.pdf"
        right = temp / "right-69-page.pdf"
        expected_lines = build_fixture(left, "LEFT")
        build_fixture(right, "RIGHT")
        app, base, _identity = helper.start_server(temp / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Local test server did not start")

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/compare-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files([str(left), str(right)])
                page.wait_for_function("window.state?.files?.length === 2", timeout=30000)
                page.wait_for_function("document.querySelector('#run-button') && !document.querySelector('#run-button').disabled", timeout=15000)
                toggle = page.locator("#client-privacy-toggle")
                if not toggle.is_checked():
                    toggle.check(force=True)
                page.locator("#run-button").click()
                browser_warning = page.locator(".app-confirm-dialog")
                try:
                    browser_warning.wait_for(state="visible", timeout=180000)
                except Exception:
                    evidence["browser_timeout_state"] = {
                        "body_text": page.locator("body").inner_text()[-1200:],
                        "run_button_text": page.locator("#run-button").inner_text(),
                        "run_button_disabled": page.locator("#run-button").is_disabled(),
                        "progress_text": page.locator("#progress-text").inner_text() if page.locator("#progress-text").count() else None,
                        "page_errors": evidence["page_errors"],
                        "console_errors": evidence["console_errors"],
                    }
                    page.screenshot(path=str(OUT / "browser-id368-large-compare-timeout.png"), full_page=True)
                    raise
                warning_text = browser_warning.inner_text()
                assert "too large for the browser" in warning_text.lower(), warning_text
                evidence["browser_mode"] = {
                    "warning": warning_text,
                    "no_false_success": not page.locator("#result-download-link").is_visible(),
                    "document_pages_each": 69,
                    "extracted_lines_each": expected_lines,
                }

                # The app explicitly asks consent to retry this oversized
                # browser comparison using temporary server processing.
                page.locator(".app-confirm-dialog .app-confirm-accept").click()
                page.locator("#result-download-link").wait_for(state="visible", timeout=90000)
                with page.expect_download(timeout=30000) as download_event:
                    page.locator("#result-download-link").click()
                download = download_event.value
                output = OUT / download.suggested_filename
                download.save_as(output)
                report = output.read_text(encoding="utf-8")
                # Text extraction inserts one blank separator between pages.
                expected_changed_lines = (expected_lines + 68) * 2
                assert f"Verdict: {expected_changed_lines} changed text lines found." in report, report[:1000]
                assert "-LEFT-PAGE-01-LINE-001 UNIQUE DETAIL" in report
                assert "+RIGHT-PAGE-69-LINE-030 UNIQUE DETAIL" in report
                evidence["server_mode"] = {
                    "download": download.suggested_filename,
                    "bytes": output.stat().st_size,
                    "verdict_checked": f"Verdict: {(expected_lines + 68) * 2} changed text lines found." in report,
                    "left_content_checked": "-LEFT-PAGE-01-LINE-001 UNIQUE DETAIL" in report,
                    "right_content_checked": "+RIGHT-PAGE-69-LINE-030 UNIQUE DETAIL" in report,
                }
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                page.screenshot(path=str(OUT / "browser-id368-large-compare-fallback.png"), full_page=False)
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id368-large-compare-fallback.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
