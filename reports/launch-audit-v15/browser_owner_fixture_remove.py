"""Remove the final page from the supplied edited PDF in Chromium."""
from __future__ import annotations

import fitz
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\edited_notes-69page.pdf")
HELPER_PATH = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("owner_remove_helpers", HELPER_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def texts(path: Path) -> list[str]:
    with fitz.open(path) as document:
        return [page.get_text().strip() for page in document]


def main() -> None:
    original = texts(SOURCE)
    assert len(original) == 68
    results = []
    with tempfile.TemporaryDirectory(prefix="paperplane-owner-remove-") as temp:
        directory = Path(temp)
        app, base, _ = helpers.start_server(directory)
        try:
            port = int(urlsplit(base).port)
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local app exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local app did not become ready")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                for number in (1, 2):
                    context = browser.new_context(accept_downloads=True)
                    page = context.new_page()
                    page_errors = []
                    page.on("pageerror", lambda error: page_errors.append(str(error).splitlines()[0][:180]))
                    page.goto(base + "/remove-pages-pdf", wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(SOURCE))
                    page.locator("#pages").fill("68")
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#result-download-link").click()
                    output = directory / f"owner-remove-{number}.pdf"
                    event.value.save_as(output)
                    assert texts(output) == original[:67]
                    assert not page_errors, page_errors
                    results.append({"round": number, "source_pages": 68, "output_pages": 67,
                                    "remaining_text_matches_source": True, "page_errors": page_errors})
                    context.close()
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except Exception:
                app.kill()
                app.wait(timeout=5)
    report = Path(__file__).with_name("browser-owner-fixture-remove.json")
    report.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
