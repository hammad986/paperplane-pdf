"""Two-round local Chromium acceptance for 10-page Spanish/Hindi fallback.

The primary provider is controlled to return HTTP 429; the configured
secondary provider returns deterministic translations through the real
provider dispatcher, Translate endpoint, UI and downloaded PDF path.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError

import fitz
import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def make_ten_page_source(path: Path) -> None:
    with fitz.open() as document:
        for page_number in range(1, 11):
            page = document.new_page()
            page.insert_text((72, 90),
                             f"SOURCE-PAGE-{page_number:03d} The Paperplane service is ready for review.",
                             fontsize=12)
        document.save(path)


with TemporaryDirectory(prefix="paperplane-id1-10page-") as temp:
    temp_root = Path(temp)
    data_dir = temp_root / "data"
    data_dir.mkdir()
    source = temp_root / "test-text-10page-controlled.pdf"
    make_ten_page_source(source)
    os.environ.update({
        "PAPERPLANE_SKIP_DOTENV": "1",
        "PAPERPLANE_ENV": "development",
        "PAPERPLANE_DATA_DIR": str(data_dir),
        "PAPERPLANE_ADMIN_KEY": "synthetic-local-admin-key",
        "PAPERPLANE_ADMIN_CODE": "synthetic-local-admin-code",
        "PAPERPLANE_SECURE_COOKIES": "false",
        "BLUESMINDS_API_KEY": "synthetic-primary-key",
    })
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ai_engine
    import persistence
    from server import app

    persistence.init_db()
    primary = {"provider": "openai_compatible", "base_url": "https://primary.controlled.test/v1",
               "model": "primary-model", "api_key": "synthetic-primary-key"}
    fallback = {"provider": "openrouter", "base_url": "https://fallback.controlled.test/v1",
                "model": "fallback-model", "api_key": "synthetic-fallback-key"}
    ai_engine._runtime_ai_config = lambda: {**primary, "fallback": fallback}
    ai_engine._current_bluesminds_api_key = lambda: "synthetic-primary-key"
    calls = {"primary_429": 0, "fallback_ok": 0, "undercoverage_mode": False}

    class FakeResponse:
        status = 200
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def controlled_open(request, timeout):
        if "primary.controlled.test" in request.full_url:
            calls["primary_429"] += 1
            raise HTTPError(request.full_url, 429, "synthetic throttling",
                            {"Retry-After": "0"}, None)
        if "fallback.controlled.test" not in request.full_url:
            raise AssertionError("provider request escaped the controlled endpoints")
        wire = json.loads(request.data.decode("utf-8"))
        system_prompt = wire["messages"][0]["content"].lower()
        target_hindi = "hindi" in system_prompt or "hi" in system_prompt
        inputs = json.loads(wire["messages"][1]["content"])
        translations = []
        for item in inputs:
            if calls["undercoverage_mode"]:
                if str(item["id"]) == "0":
                    translations.append({"id": item["id"], "text": "Este es un párrafo grande traducido." * 15})
                continue
            import re
            match = re.search(r"SOURCE-PAGE-(\d{3})", item["text"])
            page_num = match.group(1) if match else f"{int(item['id']) + 1:03d}"
            translated = (f"पृष्ठ {page_num}: सेवा तैयार है।" if target_hindi
                          else f"Página {page_num}: El servicio está listo.")
            if target_hindi:
                translated = f"प्लेन PDF टेस्ट {translated}"
            translations.append({"id": item["id"], "text": translated})
        calls["fallback_ok"] += 1
        content = json.dumps({"translations": translations}, ensure_ascii=False)
        return FakeResponse({"choices": [{"message": {"content": content}}]})

    ai_engine._open_ai_request = controlled_open
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2): break
            except OSError: time.sleep(.1)
        else: raise RuntimeError("local Uvicorn app did not start")

        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                for language, value, expected in (
                    ("Spanish", "es", "Página"),
                    ("Hindi", "hi", "पृष्ठ"),
                ):
                    context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    statuses = []
                    page.on("response", lambda response: statuses.append(response.status)
                            if "/api/ai/translate" in response.url else None)
                    response = page.goto(f"http://127.0.0.1:{port}/translate-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.wait_for_function("window.state && state.operation === 'translate'")
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#target_language").select_option(label=f"{value} ({language})")
                    page.locator("#run-button").click()
                    page.locator("#result-content a.btn-download").wait_for(state="visible", timeout=90000)
                    result_copy = page.locator("#result-meta").inner_text()
                    assert "100% character coverage" in result_copy and "100% text block coverage" in result_copy, result_copy
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#result-content a.btn-download").click()
                    artifact = temp_root / f"round-{round_no}-{value}.pdf"
                    event.value.save_as(artifact)
                    with fitz.open(artifact) as translated_pdf:
                        texts = [p.get_text() for p in translated_pdf]
                        assert translated_pdf.page_count == 10
                        assert all(expected in text for text in texts), {"language": language, "texts": texts}
                        hindi_markers = []
                        if value == "hi":
                            hindi_markers = [marker for marker in ("प्लेन", "टेस्ट")
                                             if all(marker in text for text in texts)]
                            assert len(hindi_markers) == 2, texts
                            assert not any(marker in "\n".join(texts) for marker in ("�", "Ã", "à¤")), texts
                        assert not any("SOURCE-PAGE-" in text for text in texts)
                    assert statuses and statuses[-1] == 200, statuses
                    assert not errors, errors
                    results.append({"round": round_no, "language": language, "http_status": statuses[-1],
                                    "pages": len(texts), "all_pages_searchable_in_target_language": True,
                                    "hindi_download_markers": hindi_markers,
                                    "source_markers_removed": True, "download_bytes": artifact.stat().st_size,
                                    "page_errors": errors})
                    if round_no == 2 and value == "hi":
                        page.screenshot(path=str(OUT / "id1-10page-hindi-fallback.png"))
                    context.close()
            assert len(results) == 4
            assert calls["primary_429"] >= 4 and calls["fallback_ok"] >= 4, calls
            # The first block dominates character count; translating it alone used
            # to pass the character-only gate while leaving three blocks untouched.
            imbalanced = temp_root / "imbalanced-coverage.pdf"
            long_source = "This source paragraph contains important document content. " * 15
            with fitz.open() as source_doc:
                page = source_doc.new_page()
                page.insert_textbox(fitz.Rect(72, 72, 540, 270), long_source, fontsize=10)
                for y, value in [(340, "Alpha"), (390, "Bravo"), (440, "Charlie")]:
                    page.insert_text((72, y), value)
                source_doc.save(imbalanced)
            ai_engine._translation_chunks = lambda value: [value]
            calls["undercoverage_mode"] = True
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/translate-pdf", wait_until="domcontentloaded")
            page.wait_for_function("window.state && state.operation === 'translate'")
            page.locator("#file-input").set_input_files(str(imbalanced))
            page.locator("#target_language").select_option(label="es (Spanish)")
            with page.expect_response(lambda response: "/api/ai/translate" in response.url) as response_wait:
                page.locator("#run-button").click()
            rejected = response_wait.value
            rejected_body = rejected.json()
            assert rejected.status == 422 and "25% of text blocks" in rejected_body.get("detail", ""), rejected_body
            assert not page.locator("#result-content a.btn-download").count()
            assert not errors, errors
            evidence_coverage = {"http_status": rejected.status, "detail": rejected_body.get("detail"),
                                 "download_offered": False, "translated_character_fraction_if_accepted": "over 50%",
                                 "translated_block_fraction": "25%", "page_errors": errors}
            (OUT / "browser-id1-imbalanced-coverage.json").write_text(
                json.dumps(evidence_coverage, ensure_ascii=False, indent=2), encoding="utf-8")
            page.screenshot(path=str(OUT / "id1-imbalanced-coverage-rejected.png"), full_page=True)
            context.close()
            calls["undercoverage_mode"] = False
            browser.close()
        assert len(results) == 4
        evidence = {"fixture": "synthetic 10-page text PDF matching the named acceptance shape; exact owner fixture unavailable",
                    "provider_mode": "controlled primary HTTP 429 on every primary attempt; configured secondary returns valid translations",
                    "provider_calls": calls, "results": results, "imbalanced_coverage_rejection": evidence_coverage}
        (OUT / "browser-id1-10page-rate-limit-fallback.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=10)
