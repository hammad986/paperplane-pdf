"""Run controlled-provider translation and summary on the supplied PDF."""
from __future__ import annotations

import fitz
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\edited_notes-69page.pdf")
HELPER_PATH = ROOT / "scripts" / "browser_v14_smoke.py"
spec = importlib.util.spec_from_file_location("owner_ai_helpers", HELPER_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def main() -> None:
    with fitz.open(SOURCE) as source:
        source_pages = source.page_count
        textual_pages = sum(bool(page.get_text().strip()) for page in source)
    assert source_pages == 68 and textual_pages > 0
    results = []
    with tempfile.TemporaryDirectory(prefix="paperplane-owner-ai-") as temp:
        directory = Path(temp)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        identity_file = directory / "identities.json"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(48),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32), V14_IDENTITIES=str(identity_file))
        app = subprocess.Popen([sys.executable, "-c", helpers.BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local AI test server exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local AI test server did not start")
            tokens = json.loads(identity_file.read_text())
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": tokens["student_pro"],
                                      "url": base, "httpOnly": True}])
                page = context.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(str(error).splitlines()[0][:180]))
                for number in (1, 2):
                    for lang, target in (("es", "Hola mundo"), ("hi", "भारत सरकार")):
                        page.goto(base + "/translate-pdf", wait_until="domcontentloaded")
                        page.locator("#file-input").set_input_files(str(SOURCE))
                        page.locator("#target_language").select_option(label=f"{lang} ({'Spanish' if lang == 'es' else 'Hindi'})")
                        page.locator("#run-button").click()
                        link = page.get_by_role("link", name="Download translated PDF")
                        link.wait_for(state="visible", timeout=60000)
                        with page.expect_download(timeout=30000) as event:
                            link.click()
                        output = directory / f"owner-translation-{lang}-{number}.pdf"
                        event.value.save_as(output)
                        with fitz.open(output) as translated:
                            assert translated.page_count == source_pages
                            nonempty = [sheet.get_text().strip() for sheet in translated if sheet.get_text().strip()]
                            assert len(nonempty) == textual_pages
                            assert all(target in text for text in nonempty)
                        results.append({"round": number, "kind": "translate", "language": lang,
                                        "pages": source_pages, "textual_pages": textual_pages,
                                        "download_content_verified": True})
                for number in (1, 2):
                    page.goto(base + "/summarize-pdf", wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(SOURCE))
                    page.locator("#run-button").click()
                    page.get_by_text("Grounded document summary.", exact=False).first.wait_for(timeout=60000)
                    results.append({"round": number, "kind": "summary", "input_pages": source_pages,
                                    "controlled_provider_result_visible": True})
                assert not page_errors, page_errors
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except Exception:
                app.kill()
                app.wait(timeout=5)
    report = Path(__file__).with_name("browser-owner-fixture-ai.json")
    report.write_text(json.dumps({"results": results, "page_errors": page_errors}, indent=2), encoding="utf-8")
    print(json.dumps({"results": results, "page_errors": page_errors}, indent=2))


if __name__ == "__main__":
    main()
