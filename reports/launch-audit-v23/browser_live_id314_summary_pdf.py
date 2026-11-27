from __future__ import annotations
import json
from pathlib import Path
import sys
import fitz
from playwright.sync_api import sync_playwright

BASE = "https://paperplane.qd.je"
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "v23-id2-69-pages.pdf"
RESULT = OUT / "browser-live-id314-summary-pdf.json"
DOWNLOAD = OUT / "live-id314-executive-brief.pdf"
ROUND = sys.argv[1] if len(sys.argv) > 1 else "round1"

def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/ai/capabilities", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"executive_brief_available": True, "reason": None})))
        page.goto(BASE + "/ai-intelligence", wait_until="domcontentloaded")
        page.locator("#ai-file-input").set_input_files(str(FIXTURE))
        page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=30000)
        with page.expect_response(lambda r: "/api/ai/summarize" in r.url, timeout=180000) as response_wait:
            page.locator("#trigger-summary-btn").click()
        response = response_wait.value
        page.wait_for_function("document.querySelector('#summary-display')?.innerText.trim().length > 0", timeout=180000)
        summary = page.locator("#summary-display").inner_text()
        with page.expect_download(timeout=30000) as download_wait:
            page.locator("#download-summary-pdf-btn").click()
        download = download_wait.value
        download.save_as(str(DOWNLOAD))
        with fitz.open(DOWNLOAD) as pdf:
            extracted = "\n".join(p.get_text() for p in pdf)
            pages = pdf.page_count
        checks = {
            "summary_status": response.status,
            "summary_nonempty": bool(summary.strip()),
            "download_suggested_filename": download.suggested_filename,
            "download_exists": DOWNLOAD.exists(),
            "download_bytes": DOWNLOAD.stat().st_size if DOWNLOAD.exists() else 0,
            "pdf_page_count": pages,
            "pdf_text_nonempty": bool(extracted.strip()),
            "pdf_contains_summary_heading": "Offline Analysis" in extracted,
            "pdf_contains_first_document_finding": "Quarterly Operations Review" in extracted and "[Page 1]" in extracted,
            "pdf_contains_final_document_finding": "Quarterly Operations Review" in extracted and "[Page 69]" in extracted,
            "page_errors": errors,
        }
        (OUT / "browser-live-id314-summary-pdf.png").write_bytes(page.screenshot())
        browser.close()
    RESULT = OUT / f"browser-id314-summary-pdf-{ROUND}.json"
    RESULT.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    if checks["summary_status"] != 200 or not checks["summary_nonempty"] or not checks["download_exists"] or checks["download_bytes"] < 500 or checks["pdf_page_count"] < 1 or not checks["pdf_text_nonempty"] or not checks["pdf_contains_summary_heading"] or not checks["pdf_contains_first_document_finding"] or not checks["pdf_contains_final_document_finding"] or checks["page_errors"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
