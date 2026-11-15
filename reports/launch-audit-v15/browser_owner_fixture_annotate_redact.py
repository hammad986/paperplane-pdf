"""Compare annotation and irreversible redaction on the supplied PDF."""
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
spec = importlib.util.spec_from_file_location("owner_annotate_helpers", HELPER_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> None:
    with fitz.open(SOURCE) as source:
        source_pages = source.page_count
        source_text = [page.get_text() for page in source]
    assert source_pages == 68 and sum(text.count("Machine") for text in source_text) > 0
    results = []
    with tempfile.TemporaryDirectory(prefix="paperplane-owner-redact-") as temp:
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
                    page.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'server')")
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:180]))

                    page.goto(base + "/annotate-pdf", wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(SOURCE))
                    page.locator("#annot_type").select_option("highlight")
                    page.locator("#page").fill("1")
                    page.locator("#text").fill("Machine")
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    with page.expect_download(timeout=30000) as annotation_event:
                        page.locator("#result-download-link").click()
                    annotation_file = directory / f"annotated-{number}.pdf"
                    annotation_event.value.save_as(annotation_file)
                    with fitz.open(annotation_file) as annotated:
                        assert annotated.page_count == source_pages
                        annotation_count = sum(len(list(p.annots() or [])) for p in annotated)
                        assert annotation_count > 0
                        assert "Machine" in "\n".join(p.get_text() for p in annotated)

                    page.goto(base + "/redact-pdf", wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(SOURCE))
                    page.locator("#terms").fill("Machine")
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=60000)
                    with page.expect_download(timeout=30000) as redaction_event:
                        page.locator("#result-download-link").click()
                    redacted_file = directory / f"redacted-{number}.pdf"
                    redaction_event.value.save_as(redacted_file)
                    with fitz.open(redacted_file) as redacted:
                        redacted_text = "\n".join(p.get_text() for p in redacted)
                        assert redacted.page_count == source_pages
                        assert "Machine" not in redacted_text
                    assert not errors, errors
                    results.append({"round": number, "source_pages": source_pages,
                                    "annotation_count": annotation_count,
                                    "annotated_source_text_preserved": True,
                                    "redaction_removed_all_keyword_text": True,
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
    report = Path(__file__).with_name("browser-owner-fixture-annotate-redact.json")
    report.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
