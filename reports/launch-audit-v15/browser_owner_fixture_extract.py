"""Extract page 68 from the supplied edited PDF in Studio and inspect output."""
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
spec = importlib.util.spec_from_file_location("owner_extract_helpers", HELPER_PATH)
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
    with tempfile.TemporaryDirectory(prefix="paperplane-owner-extract-") as temp:
        app, base, identities = helpers.start_server(Path(temp))
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
                    context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1],
                                          "url": base, "httpOnly": True}])
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:180]))
                    page.goto(base + "/studio", wait_until="domcontentloaded")
                    page.locator("#studio-file-input").set_input_files(str(SOURCE))
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'",
                                           timeout=30000)
                    page.locator(".organizer-thumb-card[data-page='68']").wait_for(state="visible", timeout=30000)
                    page.locator("#btn-mode-organize").click()
                    page.locator(".organizer-thumb-card[data-page='68'] .thumb-checkbox-label").click()
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#batch-extract-btn").click()
                    output = Path(temp) / f"owner-extract-{number}.pdf"
                    event.value.save_as(output)
                    assert texts(output) == [original[67]]
                    page.locator("#studio-download-feedback a").wait_for(state="visible", timeout=10000)
                    assert not errors, errors
                    results.append({"round": number, "source_pages": 68, "extracted_pages": 1,
                                    "selected_page_text_verified": True, "retry_link_visible": True,
                                    "page_errors": errors})
                    context.close()
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except Exception:
                app.kill()
                app.wait(timeout=5)
    report = Path(__file__).with_name("browser-owner-fixture-extract.json")
    report.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
