"""Exercise the 69-page Executive Brief through a local Chromium browser."""
from __future__ import annotations

import json
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8501"
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "v23-id2-69-pages.pdf"


def make_fixture() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as pdf:
        for page_num in range(1, 70):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Quarterly Operations Review — Page {page_num}")
            page.insert_text((72, 112), f"Unique verified fact for source page {page_num}: completion rate is {page_num} percent.")
            if page_num == 69:
                page.insert_text((72, 152), "Final page decision: retain all 69 page records for final audit.")
        pdf.save(FIXTURE)


def main() -> None:
    make_fixture()
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
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
        def measure_layout(viewports):
            measured = []
            for width, height in viewports:
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(120)
                result = page.evaluate("""() => {
                  const pick = text => [...document.querySelectorAll('.ai-chat-card')]
                    .find(card => card.innerText.includes(text));
                  const rect = element => {
                    const box = element?.getBoundingClientRect();
                    return box ? {left: Math.round(box.left), right: Math.round(box.right), width: Math.round(box.width)} : null;
                  };
                  return {documentWidth: document.documentElement.scrollWidth,
                    viewportWidth: innerWidth,
                    chat: rect(document.querySelector('#chat-messages')?.closest('.ai-chat-card')),
                    metadata: rect(pick('Smart Metadata Extraction')),
                    summary: rect(pick('Executive Summarizer'))};
                }""")
                measured.append({"viewport": f"{width}x{height}", **result})
            return measured

        viewports = ((390, 844), (820, 900), (1280, 720), (1920, 1080))
        before_summary_layout = measure_layout(viewports)
        page.set_viewport_size({"width": 1280, "height": 720})
        with page.expect_response(lambda response: "/api/ai/summarize" in response.url, timeout=180000) as response_info_wait:
            page.locator("#trigger-summary-btn").click()
        summary_response = response_info_wait.value
        response_info = {"status": summary_response.status, "body": summary_response.json()}
        page.wait_for_function("document.querySelector('#summary-display')?.innerText.includes('Offline Analysis')", timeout=180000)
        body = response_info.get("body", {})
        citations = body.get("citations", [])
        summary = str(body.get("summary", ""))
        mode_badge = page.locator("#summary-mode-badge").inner_text()
        evidence = {
            "local_url": BASE + "/ai-intelligence",
            "fixture_pages": 69,
            "http_status": response_info.get("status"),
            "summary_mode": body.get("summary_mode"),
            "citations_count": len(citations),
            "citation_min": min(citations) if citations else None,
            "citation_max": max(citations) if citations else None,
            "cites_first_page": 1 in citations,
            "cites_final_page": 69 in citations,
            "offline_mode_explicit": body.get("summary_mode") == "offline_extractive" and "Offline Analysis" in summary,
            "ui_badge_matches_offline_mode": mode_badge == "Offline Analysis",
            "ui_does_not_claim_synthesis": "synthesis" not in mode_badge.lower(),
            "final_page_fact_present": "69 page records" in summary or "Page 69" in summary,
            "summary_headings": summary.count("Executive Summary"),
            "ui_mode_badge": mode_badge,
            "page_errors": errors,
        }
        after_summary_layout = measure_layout(viewports)
        layout_checks = []
        for before, after in zip(before_summary_layout, after_summary_layout):
            stable_columns = all(before[card] == after[card] for card in ("chat", "metadata", "summary"))
            passed = (before["documentWidth"] <= before["viewportWidth"] and
                      after["documentWidth"] <= after["viewportWidth"] and stable_columns)
            layout_checks.append({"viewport": before["viewport"], "before": before, "after": after,
                                  "columns_stable": stable_columns, "passed": passed})
        evidence["before_summary_layout"] = before_summary_layout
        evidence["post_summary_layout_checks"] = layout_checks
        page.set_viewport_size({"width": 1280, "height": 720})
        page.screenshot(path=str(OUT / "id2-summary-route.png"), full_page=True)
        # Older deployments may omit summary_mode. Verify the UI reports that
        # uncertainty without labeling it provider synthesis.
        context.route("**/api/ai/summarize", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "success", "summary": "Executive Brief\n\nA short controlled summary.", "citations": [1]}),
        ))
        page.reload(wait_until="domcontentloaded")
        page.locator("#ai-file-input").set_input_files(str(FIXTURE))
        with page.expect_response(lambda response: "/api/ai/summarize" in response.url) as missing_mode_wait:
            page.locator("#trigger-summary-btn").click()
        missing_mode_wait.value
        page.wait_for_function("document.querySelector('#summary-mode-badge')?.textContent === 'Mode Unreported'")
        evidence["missing_mode_is_neutral"] = page.locator("#summary-mode-badge").inner_text() == "Mode Unreported"

        context.route("**/api/ai/summarize", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "success", "summary": "Executive Brief\n\nA provider summary.", "citations": [1], "summary_mode": "provider_synthesized"}),
        ))
        page.reload(wait_until="domcontentloaded")
        page.locator("#ai-file-input").set_input_files(str(FIXTURE))
        with page.expect_response(lambda response: "/api/ai/summarize" in response.url) as provider_mode_wait:
            page.locator("#trigger-summary-btn").click()
        provider_mode_wait.value
        page.wait_for_function("document.querySelector('#summary-mode-badge')?.textContent === 'AI Synthesis'")
        evidence["provider_mode_is_labeled_synthesis"] = page.locator("#summary-mode-badge").inner_text() == "AI Synthesis"
        page.screenshot(path=str(OUT / "id2-summary-mode-mapping.png"), full_page=True)
        (OUT / "browser-id2-69page-summary.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        browser.close()
    print(json.dumps(evidence, indent=2))
    if evidence["http_status"] != 200 or evidence["summary_mode"] != "offline_extractive" or not evidence["cites_first_page"] or not evidence["cites_final_page"] or not evidence["offline_mode_explicit"] or not evidence["ui_badge_matches_offline_mode"] or not evidence["ui_does_not_claim_synthesis"] or not evidence["final_page_fact_present"] or not evidence["missing_mode_is_neutral"] or not evidence["provider_mode_is_labeled_synthesis"] or not all(item["passed"] for item in evidence["post_summary_layout_checks"]) or evidence["page_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
