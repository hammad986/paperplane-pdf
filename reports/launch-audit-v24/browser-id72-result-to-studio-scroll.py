"""Check the mobile result-to-Studio handoff resets scroll and renders output."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

import fitz
from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent / "browser-id72-result-to-studio-scroll.json"
errors: list[str] = []
rounds: list[dict[str, object]] = []
with tempfile.TemporaryDirectory(prefix="paperplane-id72-") as temp_dir:
    source = Path(temp_dir) / "scroll-handoff.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Studio handoff page marker")
        document.save(source)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for attempt in (1, 2):
            page = browser.new_page(viewport={"width": 390, "height": 844}, accept_downloads=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto("http://127.0.0.1:8766/grayscale-pdf", wait_until="domcontentloaded")
            page.locator("#file-input").set_input_files(str(source))
            page.locator("#run-button").click()
            page.locator("#result-view-studio-btn").wait_for(state="visible", timeout=60_000)
            page.evaluate("window.scrollTo(0, 500)")
            scroll_before = page.evaluate("window.scrollY")
            page.locator("#result-view-studio-btn").click()
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1'", timeout=30_000)
            page.wait_for_timeout(300)
            observed = page.evaluate("""async () => {
              const doc = window.state?.studio?.pdfDoc;
              const page = doc && await doc.getPage(1);
              const text = page && await page.getTextContent();
              const toolbar = document.querySelector('.studio-toolbar').getBoundingClientRect();
              return {
                view: document.querySelector('#app-shell').className,
                windowScrollY: window.scrollY,
                mainScrollTop: document.querySelector('.main-area')?.scrollTop || 0,
                pageCount: doc?.numPages || 0,
                pageText: text?.items.map(item => item.str).join(' ') || '',
                toolbarVisible: toolbar.top >= 0 && toolbar.bottom <= innerHeight,
                noHorizontalOverflow: document.documentElement.scrollWidth <= innerWidth
              };
            }""")
            rounds.append({"round": attempt, "scroll_before_handoff": scroll_before, **observed})
            page.close()
        build = "app.js?v=191"
        browser.close()
result = {
    "build": build,
    "viewport": {"width": 390, "height": 844},
    "rounds": rounds,
    "browser_errors": errors,
    "passed": len(rounds) == 2 and all(row["scroll_before_handoff"] > 0 and row["view"].endswith("studio-active") and row["windowScrollY"] == 0 and row["mainScrollTop"] == 0 and row["pageCount"] == 1 and "Studio handoff page marker" in row["pageText"] and row["toolbarVisible"] and row["noHorizontalOverflow"] for row in rounds) and not errors,
}
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
