"""Exercise browser download recovery after a complete translation-batch failure."""
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
sys.path.insert(0, str(ROOT))
temporary = TemporaryDirectory(prefix="paperplane-id1-failed-batch-")
os.environ.update({
    "PAPERPLANE_SKIP_DOTENV": "1",
    "PAPERPLANE_ENV": "development",
    "PAPERPLANE_DATA_DIR": str(Path(temporary.name) / "data"),
    "PAPERPLANE_ADMIN_KEY": "synthetic-local-admin-key",
    "PAPERPLANE_ADMIN_CODE": "synthetic-local-admin-code",
    "PAPERPLANE_SECURE_COOKIES": "false",
    "BLUESMINDS_API_KEY": "synthetic-primary-key",
})

import ai_engine  # noqa: E402
import persistence  # noqa: E402
from server import app  # noqa: E402

source = OUT / "id1-failed-batch-repair-source.pdf"
with fitz.open() as document:
    for page_number in range(1, 11):
        page = document.new_page()
        page.insert_text((72, 90),
                         f"SOURCE-PAGE-{page_number:03d} The Paperplane service is ready for review.",
                         fontsize=12)
    document.save(source)

# All ten page blocks fit in one initial batch, forcing recovery to make five
# two-segment requests; the pre-fix four-request cap left two source blocks.
ai_engine.TRANSLATION_BATCH_SIZE = 20
original_translate_pdf_layout = ai_engine.translate_pdf_layout
translation_reports: list[dict] = []


def capture_translation_report(*args, **kwargs):
    result = original_translate_pdf_layout(*args, **kwargs)
    translation_reports.append(dict(kwargs.get("report") or {}))
    return result


ai_engine.translate_pdf_layout = capture_translation_report
state_lock = threading.Lock()
state = {"fail_first_batch": True, "initial_requests": 0, "repair_requests": 0, "max_batch_size": 0}


def controlled_translate(batch, *_args, **_kwargs):
    with state_lock:
        state["max_batch_size"] = max(state["max_batch_size"], len(batch))
        if state["fail_first_batch"]:
            state["initial_requests"] += 1
            state["fail_first_batch"] = False
            raise RuntimeError("Translation provider failed (upstream HTTP 504).")
        state["repair_requests"] += 1
    output = {}
    for block_id, text in batch:
        marker = next((part for part in text.split() if part.startswith("SOURCE-PAGE-")), None)
        page_number = marker.removeprefix("SOURCE-PAGE-") if marker else f"ID-{block_id:03d}"
        output[block_id] = f"Página {page_number}: El servicio de Paperplane está listo para revisión."
    return output


ai_engine._translate_text_batch = controlled_translate
persistence.init_db()
with socket.socket() as candidate:
    candidate.bind(("127.0.0.1", 0))
    port = candidate.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                       log_level="warning", access_log=False))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
try:
    for _ in range(150):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Local Uvicorn app failed to start")

    rounds = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for round_no in (1, 2):
                with state_lock:
                    state.update({"fail_first_batch": True, "initial_requests": 0,
                                  "repair_requests": 0, "max_batch_size": 0})
                report_count_before = len(translation_reports)
                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                page = context.new_page()
                errors: list[str] = []
                statuses: list[int] = []
                modes: list[str | None] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: (
                    statuses.append(response.status),
                    modes.append(response.headers.get("x-paperplane-translation-mode")),
                ) if "/api/ai/translate" in response.url else None)
                response = page.goto(f"http://127.0.0.1:{port}/translate-pdf",
                                     wait_until="domcontentloaded", timeout=30000)
                assert response and response.status == 200
                page.wait_for_function("window.state && state.operation === 'translate'")
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#target_language").select_option(label="es (Spanish)")
                page.locator("#run-button").click()
                page.locator("#result-content a.btn-download").wait_for(state="visible", timeout=90000)
                coverage = page.locator("#result-meta").inner_text()
                with page.expect_download(timeout=30000) as event:
                    page.locator("#result-content a.btn-download").click()
                artifact = Path(temporary.name) / f"round-{round_no}-translated.pdf"
                event.value.save_as(artifact)
                with fitz.open(artifact) as translated:
                    texts = [item.get_text() for item in translated]
                assert len(texts) == 10, len(texts)
                assert all(f"Página {index:03d}" in text for index, text in enumerate(texts, start=1)), texts
                assert all("SOURCE-PAGE-" not in text for text in texts), texts
                assert statuses and statuses[-1] == 200, statuses
                assert modes and modes[-1] == "translated", modes
                assert "100% text block coverage" in coverage and "100% character coverage" in coverage, coverage
                assert state["repair_requests"] == 5, state
                report = translation_reports[report_count_before]
                assert report["partial_translation_repair"] == {
                    "requests": 5,
                    "segments_requested": 10,
                    "segments_recovered": 10,
                    "segments_missing": 10,
                    "segments_remaining": 0,
                    "segments_deferred": 0,
                }, report.get("partial_translation_repair")
                assert any("smaller retries recovered all affected text" in warning
                           for warning in report["warnings"]), report.get("warnings")
                assert not errors, errors
                rounds.append({"round": round_no, "http_status": statuses[-1], "translation_mode": modes[-1],
                               "page_count": len(texts), "page_order_and_translation_checked": True,
                               "source_removed_from_all_pages": True, "coverage": coverage,
                               "translation_repair_report": report["partial_translation_repair"],
                               "warnings": report["warnings"],
                               "provider_state": dict(state), "page_errors": errors,
                               "download_bytes": artifact.stat().st_size})
                context.close()
        browser.close()
finally:
    server.should_exit = True
    thread.join(timeout=10)

payload = {"source": source.name, "controlled_failure": "first entire provider batch returns HTTP 504",
           "rounds": rounds}
(OUT / "browser-id1-failed-batch-repair.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
source.unlink(missing_ok=True)
temporary.cleanup()
print(json.dumps({"rounds": len(rounds), "all_downloads_content_checked": True,
                  "evidence": "browser-id1-failed-batch-repair.json"}, indent=2))
assert len(rounds) == 2
