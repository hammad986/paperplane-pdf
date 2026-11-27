"""Browser regression for actionable, accessible translation warning copy."""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main() -> None:
    with TemporaryDirectory(prefix="paperplane-translation-warning-") as temp:
        temp_path = Path(temp)
        data_dir = temp_path / "data"
        data_dir.mkdir()
        os.environ.update({
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data_dir),
            "PAPERPLANE_ADMIN_KEY": "local-translation-warning-key",
            "PAPERPLANE_ADMIN_CODE": "local-translation-warning-code",
            "PAPERPLANE_SECURE_COOKIES": "false",
            "BLUESMINDS_API_KEY": "local-controlled-provider-key",
        })
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import ai_engine
        import persistence
        from server import app

        persistence.init_db()
        provider_calls = []
        force_warning = [True]

        def controlled_provider_call(system_prompt, user_prompt, **_kwargs):
            items = json.loads(user_prompt)
            provider_calls.append(len(items))
            if len(items) > 1 and force_warning[0]:
                raise RuntimeError("upstream HTTP 503")
            item = items[0]
            return json.dumps({"translations": [{"id": str(item["id"]), "text": "Página traducida correctamente."}]}, ensure_ascii=False)

        ai_engine.call_llm = controlled_provider_call
        ai_engine.TRANSLATION_BATCH_SIZE = 2

        source = temp_path / "warning-source.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 90), "FIRST SOURCE TEXT BLOCK FOR WARNING REGRESSION", fontsize=12)
            page.insert_text((72, 130), "SECOND SOURCE TEXT BLOCK FOR WARNING REGRESSION", fontsize=12)
            page.insert_text((72, 170), "THIRD SOURCE TEXT BLOCK FOR WARNING REGRESSION", fontsize=12)
            page.insert_text((72, 210), "FOURTH SOURCE TEXT BLOCK FOR WARNING REGRESSION", fontsize=12)
            pdf.save(source)
        precision_pdf = temp_path / "precision-result.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 90), "Controlled translated output for coverage display.")
            pdf.save(precision_pdf)

        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
        worker = threading.Thread(target=server.run, daemon=True)
        worker.start()
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            evidence = {"page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base + "/translate-pdf", wait_until="domcontentloaded", timeout=30000)
                assert response and response.status == 200
                served_app_src = page.locator('script[src*="/assets/app.js"]').get_attribute("src")
                assert served_app_src == "/assets/app.js?v=206", served_app_src
                evidence["served_app_src"] = served_app_src
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#target_language").select_option(label="es (Spanish)")
                page.locator("#run-button").click()
                page.locator("#result-content .translation-review-note").wait_for(state="visible", timeout=60000)
                notice = page.locator("#result-content .translation-review-note")
                notice_text = notice.inner_text()
                role = notice.get_attribute("role")
                result_summary = page.locator("#result-meta").inner_text()
                download_link = page.locator("#result-content a.btn-download")
                with page.expect_download(timeout=30000) as pending:
                    download_link.click()
                output = temp_path / pending.value.suggested_filename
                pending.value.save_as(output)
                with fitz.open(output) as translated:
                    output_text = "\n".join(p.get_text() for p in translated)
                    page_count = len(translated)
                evidence.update({
                    "http_status": response.status,
                "warning_header": "2",
                    "warning_notice": notice_text,
                    "warning_role": role,
                    "result_summary": result_summary,
                    "provider_batch_sizes": provider_calls,
                    "download_valid_pdf": output.read_bytes().startswith(b"%PDF-"),
                    "download_pages": page_count,
                    "translated_marker_present": "Página traducida correctamente" in output_text,
                    "source_text_removed": "FIRST SOURCE TEXT BLOCK" not in output_text,
                })
                ai_engine.TRANSLATION_BATCH_SIZE = 4
                force_warning[0] = True
                singular_page = browser.new_page(viewport={"width": 1366, "height": 900})
                singular_page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                singular_page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                singular_page.goto(base + "/translate-pdf", wait_until="domcontentloaded", timeout=30000)
                singular_page.locator("#file-input").set_input_files(str(source))
                singular_page.locator("#target_language").select_option(label="es (Spanish)")
                singular_page.locator("#run-button").click()
                singular_page.locator("#result-content .translation-review-note").wait_for(state="visible", timeout=60000)
                evidence["singular_warning_notice"] = singular_page.locator("#result-content .translation-review-note").inner_text()
                evidence["singular_result_summary"] = singular_page.locator("#result-meta").inner_text()
                singular_page.close()

                ai_engine.TRANSLATION_BATCH_SIZE = 2
                force_warning[0] = False
                clean_page = browser.new_page(viewport={"width": 1366, "height": 900})
                clean_page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                clean_page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                clean_page.goto(base + "/translate-pdf", wait_until="domcontentloaded", timeout=30000)
                clean_page.locator("#file-input").set_input_files(str(source))
                clean_page.locator("#target_language").select_option(label="es (Spanish)")
                clean_page.locator("#run-button").click()
                clean_page.locator("#result-content a.btn-download").wait_for(state="visible", timeout=60000)
                evidence["clean_result_summary"] = clean_page.locator("#result-meta").inner_text()
                evidence["clean_warning_notice_count"] = clean_page.locator("#result-content .translation-review-note").count()
                clean_page.close()

                precision_page = browser.new_page(viewport={"width": 1366, "height": 900})
                precision_page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                precision_page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                precision_page.route("**/api/ai/translate", lambda route: route.fulfill(
                    status=200,
                    body=precision_pdf.read_bytes(),
                    headers={
                        "Content-Type": "application/pdf",
                        "X-Paperplane-Translation-Mode": "partial",
                        "X-Paperplane-Translated-Fraction": "0.99550000",
                        "X-Paperplane-Translated-Block-Fraction": "0.99545455",
                        "X-Paperplane-Translation-Warnings": "1",
                    },
                ))
                precision_page.goto(base + "/translate-pdf", wait_until="domcontentloaded", timeout=30000)
                precision_page.locator("#file-input").set_input_files(str(source))
                precision_page.locator("#target_language").select_option(label="es (Spanish)")
                precision_page.locator("#run-button").click()
                precision_page.locator("#result-content a.btn-download").wait_for(state="visible", timeout=30000)
                evidence["partial_coverage_precision"] = {
                    "result_title": precision_page.locator("#result-title").inner_text(),
                    "result_summary": precision_page.locator("#result-meta").inner_text(),
                    "result_message": precision_page.locator("#result-content").inner_text(),
                }
                precision_page.close()
                browser.close()
            evidence["result"] = (
                evidence["http_status"] == 200
                and evidence["warning_notice"] == "The translation reported 2 warnings. Review the translated PDF before sharing it."
                and evidence["singular_warning_notice"] == "The translation reported 1 warning. Review the translated PDF before sharing it."
                and evidence["warning_role"] == "status"
                and evidence["download_valid_pdf"] and evidence["download_pages"] == 1
                and evidence["translated_marker_present"] and evidence["source_text_removed"]
                and evidence["clean_warning_notice_count"] == 0
                and evidence["partial_coverage_precision"]["result_title"] == "Partial translation ready"
                and "99.5% character coverage, 99.5% text block coverage" in evidence["partial_coverage_precision"]["result_summary"]
                and "100% character coverage" not in evidence["partial_coverage_precision"]["result_message"]
                and not evidence["page_errors"] and not evidence["console_errors"]
            )
            (OUT / "browser-translation-warning-notice.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(evidence, indent=2, ensure_ascii=False))
            if not evidence["result"]:
                raise SystemExit(1)
        finally:
            server.should_exit = True
            worker.join(timeout=5)


if __name__ == "__main__":
    main()



