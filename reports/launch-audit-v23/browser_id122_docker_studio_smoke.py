"""Content-check the 69-page Studio export in the latest production Docker image."""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
BASE = "http://127.0.0.1:18502"
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
with fitz.open(SOURCE) as source:
    expected = [page.get_text() for page in source]
assert len(expected) == 69
rounds = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    for round_no in (1, 2):
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                      has_touch=True, accept_downloads=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        cdp = context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        started = perf_counter()
        response = page.goto(f"{BASE}/studio", wait_until="domcontentloaded", timeout=30000)
        assert response and response.status == 200
        page.locator("#studio-file-input").set_input_files(str(SOURCE))
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
        page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
        with page.expect_download(timeout=120000) as event:
            page.locator("#save-studio-btn").click()
        output = ROOT / "reports" / "launch-audit-v23" / f"docker-id122-round{round_no}.pdf"
        event.value.save_as(output)
        with fitz.open(output) as result:
            actual = [pdf_page.get_text() for pdf_page in result]
            assert actual == expected and len(result) == 69
        width = page.evaluate("document.documentElement.scrollWidth")
        assert width == 390 and not errors, {"width": width, "errors": errors}
        rounds.append({"round": round_no, "http_status": response.status, "elapsed_seconds": round(perf_counter()-started, 2),
                       "output_bytes": output.stat().st_size, "pages": len(actual),
                       "all_page_text_and_order_preserved": True, "document_width": width, "page_errors": errors})
        context.close()
    browser.close()

report = {"image": "paperplane-v23-audit:final-current",
          "image_id": "sha256:fe12cd487a4e276329db9dc2b6df26e517bb666efda59089c65fbd0eda4273a6",
          "fixture": str(SOURCE), "fixture_pages": len(expected), "cpu_throttle_rate": 4,
          "rounds": rounds}
(OUT / "browser-id122-docker-studio-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
