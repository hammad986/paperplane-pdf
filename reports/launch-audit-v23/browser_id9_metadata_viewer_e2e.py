"""Two-round local Chromium regression for Smart Metadata viewer/download races."""
from __future__ import annotations

import json
import os
import asyncio
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


with TemporaryDirectory(prefix="paperplane-id9-") as temporary:
    temp = Path(temporary)
    data_dir = temp / "data"
    data_dir.mkdir()
    fixture = temp / "smart-metadata-invoice.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "INVOICE", fontsize=18)
        page.insert_text((72, 112), "Invoice Number: INV-2026-0942")
        page.insert_text((72, 142), "Invoice Date: 2026-10-21")
        page.insert_text((72, 172), "Vendor: Northwind Paper Services")
        page.insert_text((72, 202), "Customer: Paperplane PDF")
        page.insert_text((72, 232), "Subtotal: USD 400.00")
        page.insert_text((72, 262), "Tax: USD 40.00")
        page.insert_text((72, 292), "Total Due: USD 440.00")
        page.insert_text((72, 322), "Description: document processing services")
        doc.save(fixture)

    os.environ.update({
        "PAPERPLANE_SKIP_DOTENV": "1",
        "PAPERPLANE_ENV": "development",
        "PAPERPLANE_DATA_DIR": str(data_dir),
        "PAPERPLANE_ADMIN_KEY": "synthetic-local-admin-key",
        "PAPERPLANE_ADMIN_CODE": "synthetic-local-admin-code",
        "PAPERPLANE_SECURE_COOKIES": "false",
    })
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from server import app
    import persistence
    from fastapi.responses import JSONResponse

    persistence.init_db()
    delayed_extract = {"enabled": False, "fail_first": False}

    @app.middleware("http")
    async def delay_extraction_for_navigation_probe(request, call_next):
        if request.url.path == "/api/ai/extract" and delayed_extract["fail_first"]:
            delayed_extract["fail_first"] = False
            return JSONResponse(status_code=502, content={"detail": "Synthetic transient extraction gateway error."})
        if delayed_extract["enabled"] and request.url.path == "/api/ai/extract":
            await asyncio.sleep(1.0)
        return await call_next(request)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("local app server failed to start")

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                errors = []
                extraction_statuses = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: extraction_statuses.append(response.status)
                        if "/api/ai/extract" in response.url else None)
                response = page.goto(f"http://127.0.0.1:{port}/extract-pdf-data", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("window.state && state.operation === 'ai_extract'")
                assert page.locator("#extraction-results-modal").is_hidden()
                page.locator("#file-input").set_input_files(str(fixture))
                if round_number == 1:
                    delayed_extract["fail_first"] = True
                page.locator("#run-button").click()
                page.locator("#extraction-results-modal").wait_for(state="visible", timeout=30000)
                if round_number == 1:
                    assert extraction_statuses == [502, 200], extraction_statuses
                assert page.locator("#extraction-modal-title").inner_text() == "Invoice Extraction Results"
                assert "INV-2026-0942" in page.locator("#extraction-fields-grid").inner_text()
                grid_text = page.locator("#extraction-fields-grid").inner_text()
                assert "invoice #" in grid_text.casefold() and "INV-2026-0942" in grid_text, grid_text
                assert page.locator("#result-title").inner_text() == "Structured extraction ready"
                assert page.locator("#result-download-link").is_hidden()
                page.locator("#ext-tab-json").click()
                page.locator("#ext-view-json").wait_for(state="visible")
                json_text = page.locator("#extraction-json-code").inner_text()
                parsed = json.loads(json_text)
                assert parsed["document_type"] == "invoice"
                assert parsed["invoice_data"].get("invoice_number") == "INV-2026-0942"
                with page.expect_download(timeout=15000) as download:
                    page.locator("#extraction-export-json-btn").click()
                json_path = temp / f"round-{round_number}-metadata.json"
                download.value.save_as(json_path)
                downloaded = json.loads(json_path.read_text(encoding="utf-8"))
                assert downloaded["invoice_data"].get("invoice_number") == "INV-2026-0942"
                page.locator("#extraction-modal-done-btn").click()
                assert page.locator("#extraction-results-modal").is_hidden()
                assert page.locator("#result-title").inner_text() == "Structured extraction ready"
                navigation_race = None
                if round_number == 2:
                    delayed_extract["enabled"] = True
                    with page.expect_request("**/api/ai/extract"):
                        page.locator("#run-button").click()
                    page.evaluate("selectOperation('merge')")
                    assert page.evaluate("state.operation") == "merge"
                    page.wait_for_timeout(1400)
                    assert page.locator("#extraction-results-modal").is_hidden()
                    assert page.locator("#result").is_hidden()
                    assert page.locator("#job-cancel-btn").is_hidden()
                    navigation_race = {"delayed_response_ms": 1000, "destination_operation": "merge",
                                       "stale_modal_opened": False, "stale_result_rendered": False,
                                       "stale_cancel_control_visible": False}
                assert not errors, errors
                page.screenshot(path=str(OUT / f"id9-metadata-viewer-round{round_number}.png"), full_page=True)
                rounds.append({"round": round_number, "status": response.status,
                               "viewer_opened_on_first_run": True, "document_type": parsed["document_type"],
                               "invoice_number": downloaded["invoice_data"].get("invoice_number"),
                               "extract_http_statuses": extraction_statuses,
                               "json_download_bytes": json_path.stat().st_size,
                               "result_card_preserved_after_close": True,
                               "navigation_race": navigation_race, "page_errors": errors})
                context.close()
            browser.close()
        evidence = {"fixture": "synthetic invoice PDF; local heuristic extraction, no provider credential",
                    "rounds": rounds}
        (OUT / "browser-id9-metadata-viewer-e2e.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
    finally:
        server.should_exit = True
        thread.join(timeout=10)
