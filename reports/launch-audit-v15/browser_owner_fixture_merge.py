"""Merge the supplied edited 68-page PDF in the real local browser path."""
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
spec = importlib.util.spec_from_file_location("owner_fixture_helpers", HELPER_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def texts(path: Path) -> list[str]:
    with fitz.open(path) as document:
        return [page.get_text().strip() for page in document]


def main() -> None:
    original = texts(SOURCE)
    if len(original) != 68:
        raise AssertionError(f"Expected 68-page supplied fixture, got {len(original)}")
    rounds = []
    with tempfile.TemporaryDirectory(prefix="paperplane-owner-merge-") as temp:
        directory = Path(temp)
        second = directory / "synthetic-one-page.pdf"
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 72), "Owner fixture merge verification page")
            pdf.save(second)
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
                for round_number in (1, 2):
                    context = browser.new_context(accept_downloads=True)
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:180]))
                    page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                    with page.expect_file_chooser(timeout=5000) as chooser_event:
                        page.locator("#browse").click()
                    chooser_event.value.set_files([str(SOURCE), str(second)])
                    page.locator(".file-row-card").nth(1).wait_for(state="visible", timeout=15000)
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#result-download-link").click()
                    output = directory / f"owner-merge-{round_number}.pdf"
                    event.value.save_as(output)
                    result = texts(output)
                    assert result == original + ["Owner fixture merge verification page"]
                    assert not errors, errors
                    rounds.append({"round": round_number, "input_pages": 69, "output_pages": len(result),
                                   "file_chooser_event_used": True,
                                   "source_page_text_preserved": True, "second_document_last_page_verified": True,
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
    path = Path(__file__).with_name("browser-owner-fixture-merge.json")
    path.write_text(json.dumps({"results": rounds}, indent=2), encoding="utf-8")
    print(json.dumps({"results": rounds}, indent=2))


if __name__ == "__main__":
    main()
