"""Small, bounded live Merge diagnostic using an expendable public PDF."""
from __future__ import annotations

import json
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "launch-audit-v23" / "fixtures" / "totpdf-sample-5-pages.pdf"
OUT = HERE / "browser-live-v239-merge-diagnostic.json"


def main() -> None:
    evidence = {"site": "https://paperplane.qd.je", "fixture_bytes": FIXTURE.stat().st_size,
                "responses": [], "page_errors": [], "console_errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
        page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
        page.on("response", lambda response: evidence["responses"].append(
            {"status": response.status, "url": response.url}) if "/api/" in response.url else None)
        try:
            page.goto(evidence["site"] + "/merge-pdf", wait_until="domcontentloaded", timeout=30000)
            page.locator("#tool-title").wait_for(state="visible", timeout=30000)
            if page.locator("#client-privacy-toggle").is_checked():
                page.locator("#client-privacy-toggle").evaluate("el => el.click()")
            page.locator("#file-input").set_input_files([str(FIXTURE), str(FIXTURE)])
            evidence["run_enabled"] = page.locator("#run-button").is_enabled()
            page.locator("#run-button").click(timeout=10000)
            try:
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                evidence["download_visible"] = True
                with page.expect_download(timeout=30000) as download_event:
                    page.locator("#result-download-link").click()
                result_path = HERE / "live-v239-merge-ten-pages.pdf"
                download_event.value.save_as(result_path)
                with fitz.open(result_path) as document:
                    evidence["download_page_count"] = document.page_count
                    evidence["page_markers"] = [page.get_text().strip() for page in document]
                    evidence["content_verified"] = document.page_count == 10 and all(
                        f"page {(index % 5) + 1} of 5" in page.get_text().lower()
                        for index, page in enumerate(document)
                    )
            except Exception as error:
                evidence["download_visible"] = False
                evidence["wait_error"] = str(error).split("Call log:")[0].strip()
            evidence["visible_text"] = page.locator("body").inner_text()[-2500:]
            evidence["result_link"] = page.locator("#result-download-link").evaluate(
                "el => ({hidden: el.hidden, href: el.getAttribute('href'), text: el.innerText})")
            page.screenshot(path=str(HERE / "browser-live-v239-merge-diagnostic.png"), full_page=True)
        finally:
            browser.close()
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
