"""Check a real browser-side merge against an already-running Paperplane server."""
from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import fitz
from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="Base URL of the server being checked")
    args = parser.parse_args()
    with TemporaryDirectory() as temporary, sync_playwright() as playwright:
        directory = Path(temporary)
        paths = []
        for number in (1, 2):
            path = directory / f"source-{number}.pdf"
            with fitz.open() as pdf:
                pdf.new_page().insert_text((72, 72), f"Local merge page {number}")
                pdf.save(path)
            paths.append(path)
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        jobs = []
        page.on("request", lambda request: jobs.append(request.url)
                if request.method == "POST" and urlsplit(request.url).path == "/api/jobs" else None)
        page.goto(args.base_url.rstrip("/") + "/merge-pdf", wait_until="domcontentloaded")
        page.locator("#tool-title").wait_for(state="visible")
        assert page.evaluate("typeof window.PaperplanePdfRuntime.transformLocalPdf") == "function"
        page.locator("#file-input").set_input_files([str(path) for path in paths])
        page.locator("#run-button").click()
        link = page.locator("#result-download-link:not([hidden])")
        link.wait_for(state="visible", timeout=30000)
        with page.expect_download(timeout=30000) as event:
            link.click()
        result = directory / "merged.pdf"
        event.value.save_as(result)
        with fitz.open(result) as pdf:
            assert pdf.page_count == 2
            assert all(f"Local merge page {index + 1}" in page.get_text() for index, page in enumerate(pdf))
        assert not jobs, "Merge was sent to the server instead of running locally"
        page.goto(args.base_url.rstrip("/") + "/", wait_until="domcontentloaded", timeout=2000)
        browser.close()
    print("Browser-side merge passed: two input pages, two output pages, no job request; navigation completed within two seconds.")


if __name__ == "__main__":
    main()
