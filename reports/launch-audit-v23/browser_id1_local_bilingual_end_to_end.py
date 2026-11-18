"""Controlled-provider browser verification for the Translate P0 behavior.

This uses the real local Translate route and real browser downloads while
replacing only the upstream model call with deterministic test translations.
No external provider is contacted and no payment/account data is used.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PORT = 0


def make_source(path: Path, page_count: int) -> None:
    with fitz.open() as document:
        for page_number in range(1, page_count + 1):
            page = document.new_page()
            page.insert_text(
                (72, 90),
                f"SOURCE-PAGE-{page_number:03d} The source document contains a test sentence for translation.",
                fontsize=12,
            )
        document.save(path)


def main() -> None:
    global PORT
    with TemporaryDirectory(prefix="paperplane-id1-controlled-browser-") as temp:
        temp_path = Path(temp)
        source_dir = temp_path / "fixtures"
        data_dir = temp_path / "data"
        source_dir.mkdir()
        data_dir.mkdir()
        os.environ.update({
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data_dir),
            "PAPERPLANE_ADMIN_KEY": "local-controlled-admin-key-not-for-use",
            "PAPERPLANE_ADMIN_CODE": "local-controlled-admin-code-not-for-use",
            "PAPERPLANE_SECURE_COOKIES": "false",
            "BLUESMINDS_API_KEY": "local-controlled-provider-key-not-for-use",
        })
        sys_path = str(ROOT)
        import sys
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        import ai_engine
        import persistence
        from server import app

        persistence.init_db()

        def controlled_translation(blocks, target_language, deadline=None):
            language = str(target_language).lower()
            result = {}
            for block_id, source_text in blocks:
                import re
                match = re.search(r"SOURCE-PAGE-(\d{3})", source_text)
                page_number = int(match.group(1)) if match else block_id + 1
                if language.startswith("hi"):
                    result[block_id] = f"पृष्ठ {page_number}: अनुवाद परीक्षण सफल और सही है।"
                else:
                    result[block_id] = f"Página {page_number}: la prueba de traducción es correcta."
            return result

        ai_engine._translate_text_batch = controlled_translation

        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            PORT = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{PORT}"
        config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", access_log=False)
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        try:
            for _ in range(200):
                try:
                    with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local test server did not start")

            cases = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_number in (1, 2):
                    for page_count in (3, 69):
                        source = source_dir / f"source-{page_count}-pages.pdf"
                        make_source(source, page_count)
                        for language, value, marker in (
                            ("Spanish", "es", "Página"),
                            ("Hindi", "hi", "पृष्ठ"),
                        ):
                            context = browser.new_context(
                                viewport={"width": 1366, "height": 900},
                                accept_downloads=True,
                            )
                            page = context.new_page()
                            errors: list[str] = []
                            console_messages: list[str] = []
                            failed_requests: list[str] = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.on("console", lambda message: console_messages.append(message.text)
                                    if message.type == "error" else None)
                            page.on("requestfailed", lambda request: failed_requests.append(
                                f"{request.method} {request.url}: {request.failure}"))
                            response_status: list[int] = []
                            page.on("response", lambda response: response_status.append(response.status)
                                    if "/api/ai/translate" in response.url else None)
                            response = page.goto(base + "/translate-pdf", wait_until="domcontentloaded")
                            assert response and response.status == 200
                            page.wait_for_function("window.state && state.operation === 'translate'")
                            page.locator("#file-input").set_input_files(str(source))
                            language_label = "es (Spanish)" if value == "es" else "hi (Hindi)"
                            page.locator("#target_language").select_option(label=language_label)
                            page.locator("#run-button").click()
                            try:
                                page.locator("#result-content a.btn-download").wait_for(state="visible", timeout=45_000)
                            except Exception:
                                page.screenshot(path=str(OUT / f"id1-local-debug-round{round_number}-{page_count}-{value}.png"))
                                raise AssertionError(json.dumps({
                                    "result_visible": page.locator("#result").is_visible(),
                                    "result_text": page.locator("#result").inner_text() if page.locator("#result").count() else "missing",
                                    "progress_text": page.locator("#progress-card").inner_text() if page.locator("#progress-card").count() else "missing",
                                    "response_status": response_status,
                                    "page_errors": errors,
                                    "console_errors": console_messages,
                                    "failed_requests": failed_requests,
                                }, ensure_ascii=False, indent=2))
                            result_text = page.locator("#result").inner_text()
                            assert "Translation complete" in result_text, result_text
                            assert "100%" in result_text, result_text
                            output = temp_path / f"round-{round_number}-{page_count}-{value}.pdf"
                            with page.expect_download(timeout=30_000) as download_event:
                                page.locator("#result-content a.btn-download").click()
                            download_event.value.save_as(output)
                            with fitz.open(output) as translated:
                                assert len(translated) == page_count
                                extracted = [pdf_page.get_text() for pdf_page in translated]
                                assert all(marker in text for text in extracted), (language, page_count)
                                assert not any("SOURCE-PAGE-" in text for text in extracted)
                            assert response_status and response_status[-1] == 200, response_status
                            assert not errors, errors
                            case = {
                                "round": round_number,
                                "source_pages": page_count,
                                "language": language,
                                "http_status": response_status[-1],
                                "download_bytes": output.stat().st_size,
                                "output_pages": len(extracted),
                                "searchable_marker": marker,
                                "original_source_text_removed": True,
                                "page_errors": errors,
                            }
                            cases.append(case)
                            if round_number == 2 and page_count == 3 and value == "hi":
                                page.screenshot(path=str(OUT / "id1-local-hindi-three-page-result.png"))
                            context.close()
                browser.close()
            evidence = {
                "mode": "local controlled provider; no external AI call",
                "browser": "Chrome via Playwright",
                "rounds": 2,
                "matrix": "3-page and 69-page source × Spanish and Hindi",
                "results": cases,
                "case_count": len(cases),
            }
            assert len(cases) == 8
            (OUT / "browser-id1-local-bilingual-end-to-end.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
        finally:
            server.should_exit = True
            server_thread.join(timeout=10)


if __name__ == "__main__":
    main()
