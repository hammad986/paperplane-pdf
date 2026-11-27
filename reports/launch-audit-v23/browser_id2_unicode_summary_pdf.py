"""Probe summary PDF export with non-Latin text through Chromium."""
from __future__ import annotations

import json
import os
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright

BASE = os.environ.get("PAPERPLANE_TEST_BASE", "http://127.0.0.1:8501")
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "v23-id2-unicode-summary-source.pdf"
ROUND = os.environ.get("PAPERPLANE_ID2_UNICODE_ROUND", "current")

with fitz.open() as source:
    page = source.new_page()
    page.insert_text((72, 72), "Unicode summary PDF export probe")
    source.save(FIXTURE)

result = {"fixture": FIXTURE.name, "summary": "कार्य योजना — सुरक्षित PDF export 😊", "download": None, "page_errors": []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
    context.route("**/api/ai/capabilities", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"executive_brief_available": True, "reason": None}),
    ))
    context.route("**/api/ai/summarize", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "status": "success",
            "summary": "Executive Summary (Offline Analysis)\n\nकार्य योजना — सुरक्षित PDF export 😊",
            "citations": [1],
            "summary_mode": "offline_extractive",
        }, ensure_ascii=False),
    ))
    page.goto(BASE + "/ai-intelligence", wait_until="domcontentloaded")
    page.locator("#ai-file-input").set_input_files(str(FIXTURE))
    page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=30000)
    with page.expect_response(lambda response: "/api/ai/summarize" in response.url, timeout=30000):
        page.locator("#trigger-summary-btn").click()
    page.wait_for_function("document.querySelector('#summary-display')?.innerText.includes('कार्य योजना')", timeout=30000)
    try:
        with page.expect_download(timeout=5000) as download_wait:
            page.locator("#download-summary-pdf-btn").click()
        download = download_wait.value
        target = OUT / f"id2-unicode-{ROUND}-{download.suggested_filename}"
        download.save_as(str(target))
        if download.suggested_filename.lower().endswith(".txt"):
            extracted = target.read_text(encoding="utf-8")
            result["download"] = {
                "filename": download.suggested_filename,
                "text": extracted,
                "has_unicode": "कार्य" in extracted,
                "has_pdf_extension": False,
                "is_unicode_text_fallback": True,
            }
        else:
            with fitz.open(target) as output:
                extracted = "\n".join(item.get_text() for item in output)
                result["download"] = {
                    "filename": download.suggested_filename,
                    "pages": len(output),
                    "text": extracted,
                    "has_unicode": "कार्य" in extracted,
                    "has_pdf_extension": download.suggested_filename.endswith(".pdf"),
                    "is_unicode_text_fallback": False,
                }
    except Exception as error:
        result["download_error"] = f"{type(error).__name__}: {error}"
    result["warning_visible"] = page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else ""
    browser.close()

(OUT / f"browser-id2-unicode-summary-pdf-{ROUND}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
download_result = result.get("download") or {}
if (download_result.get("has_unicode")
        and (download_result.get("has_pdf_extension")
             or (download_result.get("is_unicode_text_fallback")
                 and "font" in result.get("warning_visible", "").lower()))
        and not result["page_errors"]):
    raise SystemExit(0)
raise SystemExit(1)
