"""One controlled, synthetic 69-page summary probe against the currently deployed app."""
from pathlib import Path
import json
import re

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "https://paperplane.qd.je"
FIXTURE = OUT / "fixtures" / "live-id2-synthetic-69-pages.pdf"
PAGE24 = "Decision after page 12: cancel the duplicate vendor work immediately. Do not spend or authorize any new payment. The approved maximum is 900000, with no currency stated."
PAGE69 = "Final deadline: deliver the signed cancellation record by 15 December 2026."


with fitz.open() as document:
    for number in range(1, 70):
        page = document.new_page(width=595, height=842)
        page.insert_text((50, 60), f"Synthetic operations review page {number} of 69.")
        page.insert_text((50, 92), f"Unique factual marker: record {number} has status verified.")
        if number == 24:
            page.insert_textbox((50, 130, 540, 300), PAGE24)
        if number == 69:
            page.insert_textbox((50, 130, 540, 240), PAGE69)
    document.save(FIXTURE, garbage=4, deflate=True)

result = {"base": BASE, "fixture": FIXTURE.name, "input_pages": 69, "content": "synthetic only"}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    page = context.new_page()
    page_errors = []
    relevant_responses = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("response", lambda response: relevant_responses.append({"status": response.status, "url": response.url}) if "/api/ai/summarize" in response.url else None)
    response = page.goto(BASE + "/ai-intelligence", wait_until="domcontentloaded", timeout=60000)
    assert response and response.status == 200, {"status": response.status if response else None}
    page.locator("#ai-file-input").set_input_files(str(FIXTURE))
    page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=60000)
    with page.expect_response(lambda item: "/api/ai/summarize" in item.url, timeout=300000) as response_info:
        page.locator("#trigger-summary-btn").click()
    api_response = response_info.value
    body = api_response.json()
    page.wait_for_function("() => document.querySelector('#summary-display')?.innerText.trim().length > 0", timeout=30000)
    visible_summary = page.locator("#summary-display").inner_text()
    summary = str(body.get("summary") or body.get("executive_summary") or "")
    citations = body.get("citations") or []
    cited_pages = []
    for citation in citations:
        if isinstance(citation, int):
            cited_pages.append(citation)
        elif isinstance(citation, dict):
            for key in ("page", "page_number", "page_num"):
                if isinstance(citation.get(key), int):
                    cited_pages.append(citation[key])
                    break
    all_text = (summary + "\n" + visible_summary).lower()
    has_cancel = bool(re.search(r"cancel|terminat|stop", all_text))
    has_spend = bool(re.search(r"900[,. ]?000|900k", all_text))
    has_deadline = bool(re.search(r"15\s+dec(?:ember)?\s+2026|2026-12-15|15/12/2026", all_text))
    result.update({
        "http_status": api_response.status,
        "response_keys": sorted(body.keys()),
        "summary_mode": body.get("summary_mode"),
        "summary_text": summary,
        "citations_count": len(citations),
        "min_cited_page": min(cited_pages) if cited_pages else None,
        "max_cited_page": max(cited_pages) if cited_pages else None,
        "page24_cancellation_retained": has_cancel,
        "page24_spending_limit_retained": has_spend,
        "page69_deadline_retained": has_deadline,
        "summary_chars": len(summary),
        "summary_mode_badge": page.locator("#summary-mode-badge").inner_text() if page.locator("#summary-mode-badge").count() else None,
        "provider_name_not_recorded": True,
        "page_errors": page_errors,
        "api_responses": relevant_responses,
    })
    if body.get("summary_mode") in ("provider_synthesis", "ai_synthesis", "provider"):
        assert has_cancel and has_spend and has_deadline, result
    assert api_response.status == 200 and not page_errors, result
    browser.close()

(OUT / "browser-live-id2-69page-provider.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
