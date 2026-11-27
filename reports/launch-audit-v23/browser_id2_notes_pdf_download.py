"""Content-check the Executive Brief path with the available real 69-page notes PDF."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import fitz
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
FIXTURE = Path(os.environ.get("PAPERPLANE_ID2_NOTES_PDF", r"C:\Users\mdham\Downloads\notes.pdf"))
BASE = os.environ.get("PAPERPLANE_TEST_BASE", "http://127.0.0.1:8501")
TARGET = os.environ.get("PAPERPLANE_ID2_NOTES_TARGET", "local")
assert FIXTURE.is_file(), f"Fixture not found: {FIXTURE}"
with fitz.open(FIXTURE) as source:
    source_pages = len(source)
    source_text = "\n".join(page.get_text() for page in source)
assert source_pages == 69
source_terms = [term for term in ("Machine Learning", "Naive Bayes", "Inductive bias")
                if term.casefold() in source_text.casefold()]

rounds = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for round_number in (1, 2):
        errors: list[str] = []
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("**/api/ai/capabilities", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"executive_brief_available": True, "reason": None}),
        ))
        page.goto(BASE + "/ai-intelligence", wait_until="domcontentloaded")
        page.locator("#ai-file-input").set_input_files(str(FIXTURE))
        page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=30000)
        with page.expect_response(lambda response: "/api/ai/summarize" in response.url, timeout=300000) as response_wait:
            page.locator("#trigger-summary-btn").click()
        response = response_wait.value
        body = response.json()
        page.wait_for_function("document.querySelector('#summary-display')?.innerText.length > 100", timeout=300000)
        summary_text = str(body.get("summary", ""))
        citations = body.get("citations", [])
        assert response.status == 200 and body.get("summary_mode") == "offline_extractive", body
        assert len(summary_text) > 1000 and min(citations or [0]) == 1 and max(citations or [0]) == 69
        assert "Offline Analysis" in page.locator("#summary-mode-badge").inner_text()
        assert any(term.casefold() in summary_text.casefold() for term in source_terms)
        with page.expect_download(timeout=30000) as download_wait:
            page.locator("#download-summary-pdf-btn").click()
        download = download_wait.value
        artifact = OUT / f"id2-notes-{TARGET}-round{round_number}-{download.suggested_filename}"
        download.save_as(str(artifact))
        if download.suggested_filename.lower().endswith(".pdf"):
            with fitz.open(artifact) as result:
                result_text = "\n".join(output_page.get_text() for output_page in result)
                page_count = len(result)
            fallback = False
        else:
            result_text = artifact.read_text(encoding="utf-8")
            page_count = None
            fallback = True
            assert "font" in page.locator(".toast-notice").inner_text().lower()
        checks = {
            "fixture_pages": source_pages,
            "http_status": response.status,
            "mode": body.get("summary_mode"),
            "summary_chars": len(summary_text),
            "citations_count": len(citations),
            "citation_min": min(citations),
            "citation_max": max(citations),
            "has_offline_label": "Offline Analysis" in result_text,
            "has_source_terms": any(term.casefold() in result_text.casefold() for term in source_terms),
            "has_page_69_citation": "Page 69" in result_text or "Pages 1-69" in result_text,
            "download_filename": download.suggested_filename,
            "download_type": "UTF-8 TXT fallback" if fallback else "PDF",
            "download_pages": page_count,
            "download_chars": len(result_text),
            "page_errors": errors,
        }
        checks["passed"] = (
            checks["http_status"] == 200 and checks["mode"] == "offline_extractive"
            and checks["citations_count"] == 69 and checks["citation_min"] == 1
            and checks["citation_max"] == 69 and checks["has_offline_label"]
            and checks["has_source_terms"] and checks["has_page_69_citation"]
            and checks["download_chars"] > 1000 and not errors
        )
        rounds.append({"round": round_number, **checks})
        context.close()
    browser.close()

evidence = {"base": BASE, "target": TARGET, "fixture": FIXTURE.name, "source_pages": source_pages, "rounds": rounds}
(OUT / f"browser-id2-notes-summary-{TARGET}.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
if not all(result["passed"] for result in rounds):
    raise SystemExit(1)
