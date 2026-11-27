"""Confirm the Organize PDF tool actually reorders pages locally as advertised."""
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
OUT = ROOT / "reports/launch-audit-v24/browser-id166-organizer-local-processing.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id166-") as temp_name:
        temp = Path(temp_name)
        source = temp / "id166-source.pdf"
        with fitz.open() as document:
            for page_number in range(1, 4):
                page = document.new_page()
                page.insert_text((72, 100), f"ID166 source page {page_number}")
            document.save(source)
        app, base, _identities = helper.start_server(temp / "data")
        evidence = {"page_errors": [], "console_errors": [], "server_job_posts": []}
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
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                page.on("request", lambda request: evidence["server_job_posts"].append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                response = page.goto(base + "/organize-pdf", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(source))
                page.wait_for_function("state.clientSideMode === true")
                evidence["processing_label"] = page.locator("#client-privacy-toggle").is_checked()
                evidence["local_help_copy"] = page.locator("#privacy-mode-support").inner_text()
                page.locator("#pages").fill("3,1,2")
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(timeout=30000)
                with page.expect_download(timeout=20000) as download_event:
                    page.locator("#result-download-link").click()
                output = temp / "organized.pdf"
                download_event.value.save_as(output)
                with fitz.open(output) as document:
                    markers = [page.get_text().strip() for page in document]
                    evidence["download"] = {
                        "filename": download_event.value.suggested_filename,
                        "pages": document.page_count,
                        "markers_in_order": markers,
                    }
                browser.close()
            evidence["http_status"] = response.status if response else None
            evidence["overall"] = "passed" if (
                evidence["http_status"] == 200
                and evidence["processing_label"] is True
                and "not uploaded" in evidence["local_help_copy"]
                and evidence["download"]["pages"] == 3
                and evidence["download"]["markers_in_order"] == [
                    "ID166 source page 3", "ID166 source page 1", "ID166 source page 2",
                ]
                and not evidence["server_job_posts"]
                and not evidence["page_errors"] and not evidence["console_errors"]
            ) else "failed"
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if evidence["overall"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
