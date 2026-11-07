from __future__ import annotations

import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
SAMPLE_PDF = OUT / "phase0_color-audit_merge.pdf"
BUTTON_TOOLS = [
    ("Page Numbers", "/add-page-numbers-to-pdf", "page_numbers"),
    ("Compare", "/compare-pdf", "compare"),
    ("Edit", "/edit-pdf", "edit"),
    ("Sign", "/sign-pdf", "sign"),
    ("Unlock", "/unlock-pdf", "unlock"),
    ("Fill Form", "/fill-pdf-form", "forms"),
    ("PDF Metadata", "/pdf-metadata", "metadata"),
    ("AI Summarize", "/summarize-pdf", "summarize"),
]


def audit_run_buttons(browser) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for width in (1366, 375):
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 900 else 812}, is_mobile=width < 600, has_touch=width < 600)
        page.on("pageerror", lambda error: errors.append({"kind": "page", "text": str(error)}))
        page.on("console", lambda message: errors.append({"kind": "console", "text": message.text}) if message.type == "error" else None)
        for name, route, operation in BUTTON_TOOLS:
            page.goto(BASE + route, wait_until="domcontentloaded")
            page.locator("#run-button").wait_for(timeout=15000)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not page.evaluate("operation => Boolean(state.operations?.[operation])", operation):
                time.sleep(0.05)
            page.locator("#file-input").set_input_files(str(SAMPLE_PDF))
            if route == "/unlock-pdf":
                page.locator("#password").fill("local-audit-only")
            page.wait_for_timeout(120)
            row = page.evaluate(
                """({name,route,width})=>{
                  const button=document.querySelector('#run-button');
                  const rect=button.getBoundingClientRect();
                  const textNode=[...button.childNodes].find(node=>node.nodeType===Node.TEXT_NODE && node.textContent.trim());
                  const text=textNode?.textContent.trim()||button.innerText.trim();
                  const words=[];
                  let match;
                  const regex=/\\S+/g;
                  while((match=regex.exec(text))){
                    const range=document.createRange();
                    range.setStart(textNode||button.firstChild,match.index);
                    range.setEnd(textNode||button.firstChild,match.index+match[0].length);
                    words.push({word:match[0],fragments:range.getClientRects().length});
                  }
                  return {name,route,viewport:width,label:text,disabled:button.disabled,buttonWidth:rect.width,buttonHeight:rect.height,clientWidth:button.clientWidth,scrollWidth:button.scrollWidth,whiteSpace:getComputedStyle(button).whiteSpace,wordBreaks:words.filter(word=>word.fragments>1),documentOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth};
                }""",
                {"name": name, "route": route, "width": width},
            )
            page.locator("#run-button").scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / f"p2-run-button-{name.lower().replace(' ','-')}-{width}.png"), full_page=False)
            rows.append(row)
        page.close()
    return {"cases": rows, "errors": errors}


def audit_sticky_heading(browser) -> dict[str, object]:
    rows = []
    errors = []
    for width in (1366, 1104):
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.on("pageerror", lambda error: errors.append({"kind": "page", "text": str(error)}))
        page.on("console", lambda message: errors.append({"kind": "console", "text": message.text}) if message.type == "error" else None)
        page.goto(BASE + "/", wait_until="domcontentloaded")
        heading = page.locator(".home-cat-section .home-cat-title").first
        # The application scrolls inside .main-area; window.scrollTo leaves it at the top.
        heading.evaluate("element => element.scrollIntoView({block: 'start', behavior: 'instant'})")
        page.wait_for_timeout(200)
        geometry = page.evaluate(
            """() => {
              const header=document.querySelector('.topbar');
              const tabs=document.querySelector('.workspace-tabs');
              const heading=document.querySelector('.home-cat-section .home-cat-title');
              const h=header.getBoundingClientRect(),t=tabs.getBoundingClientRect(),g=heading.getBoundingClientRect();
              return {viewport:innerWidth,header:{top:h.top,bottom:h.bottom,height:h.height},tabs:{top:t.top,bottom:t.bottom,width:t.width,scrollWidth:tabs.scrollWidth,clientWidth:tabs.clientWidth,height:t.height,buttons:[...tabs.querySelectorAll('.tab-pill')].map(b=>{const r=b.getBoundingClientRect();return {text:b.innerText.trim(),top:r.top,bottom:r.bottom,left:r.left,right:r.right}})},heading:{text:heading.innerText.trim(),top:g.top,bottom:g.bottom},heading_clearance:Math.round(g.top-h.bottom),heading_below_header:g.top>=h.bottom+4,documentOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth};
            }"""
        )
        page.screenshot(path=str(OUT / f"p2-sticky-heading-{width}.png"), full_page=False)
        rows.append(geometry)
        page.close()
    return {"cases": rows, "errors": errors}


def audit_metadata_result(browser) -> dict[str, object]:
    rows = []
    errors = []
    for width in (1366, 375):
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 900 else 812}, is_mobile=width < 600, has_touch=width < 600)
        page.on("pageerror", lambda error: errors.append({"kind": "page", "text": str(error)}))
        page.on("console", lambda message: errors.append({"kind": "console", "text": message.text}) if message.type == "error" else None)
        page.goto(BASE + "/ai-pdf-chat", wait_until="domcontentloaded")
        page.locator("#extraction-results-modal").wait_for(state="attached", timeout=15000)
        for topic_count in (1, 2):
            payload = {
                "document_type": "general",
                "total_pages": 10,
                "source_pages": [1, 5, 10],
                "general_data": {"title": "Ten page metadata audit sample", "document_date": None, "detected_topics": [f"Topic {index}" for index in range(topic_count)]},
                "contact": {"emails": [], "phones": []},
                "warnings": [],
            }
            page.evaluate("payload => renderExtractionResultsModal(payload)", payload)
            fields = page.locator("#extraction-fields-grid .extraction-field-card").evaluate_all("cards => cards.map(card => ({label:card.querySelector('.extraction-field-label')?.textContent.trim(),value:card.querySelector('.extraction-field-value')?.textContent.trim()}))")
            page.screenshot(path=str(OUT / f"p2-metadata-{topic_count}-topic-{width}.png"), full_page=False)
            rows.append({"viewport": width, "total_pages": payload["total_pages"], "topic_count": topic_count, "fields": fields, "document_date_row_visible": any(field["label"] == "Document Date" for field in fields), "topic_value": next((field["value"] for field in fields if field["label"] == "Detected Topics Count"), None)})
        page.close()
    return {"cases": rows, "errors": errors}


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        result = {
            "run_buttons": audit_run_buttons(browser),
            "sticky_heading": audit_sticky_heading(browser),
            "metadata_result_ui": audit_metadata_result(browser),
        }
        browser.close()

    target = OUT / "p2-remaining-checks.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(target), **result}, indent=2, ensure_ascii=False))
    button_cases = result["run_buttons"]["cases"]
    if len(button_cases) != 16 or any(case["wordBreaks"] or case["documentOverflow"] for case in button_cases):
        raise SystemExit("At least one named run button has mid-word wrapping or viewport overflow")
    if any(not case["heading_below_header"] for case in result["sticky_heading"]["cases"]):
        raise SystemExit("A scrolled section heading is covered by the sticky header")
    if any(case["document_date_row_visible"] or case["topic_value"] != f"{case['topic_count']} topic" + ("s" if case["topic_count"] != 1 else "") for case in result["metadata_result_ui"]["cases"]):
        raise SystemExit("Metadata singular/plural or absent-date display is incorrect")
    if any(result[key]["errors"] for key in ("run_buttons", "sticky_heading", "metadata_result_ui")):
        raise SystemExit("A browser/page error occurred during P2 checks")


if __name__ == "__main__":
    main()
