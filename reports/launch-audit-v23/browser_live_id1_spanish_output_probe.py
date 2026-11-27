"""Persist and inspect one synthetic live Spanish translation output."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json

import fitz
from playwright.sync_api import sync_playwright

BASE = "https://paperplane.qd.je"
OUT = Path(__file__).resolve().parent
source = OUT / "id1-live-output-probe-source.pdf"
output = OUT / "id1-live-spanish-output-probe.pdf"

with fitz.open() as document:
    for number in range(1, 11):
        page = document.new_page()
        page.insert_text(
            (72, 90),
            f"SOURCE-PAGE-{number:03d} This paperplane document is ready for review and discussion.",
            fontsize=12,
        )
    document.save(source)

evidence = {"site": BASE, "output": output.name, "http_status": None, "result_text": "", "pages": []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    page = context.new_page()
    errors = []
    statuses = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("response", lambda response: statuses.append(response.status) if "/api/ai/translate" in response.url else None)
    response = page.goto(BASE + "/translate-pdf", wait_until="domcontentloaded", timeout=45000)
    assert response and response.status == 200
    page.locator("#tool-title").wait_for(state="visible", timeout=30000)
    page.locator("#file-input").set_input_files(str(source))
    page.locator("#target_language").select_option(label="es (Spanish)")
    page.locator("#run-button").click()
    page.wait_for_function("""()=>{
      const link=document.querySelector('#result-content a.btn-download');
      const text=(document.querySelector('#result')?.innerText||'').toLowerCase();
      return (link&&!link.hidden&&link.getBoundingClientRect().width>0) || text.includes('failed') || text.includes('could not');
    }""", timeout=180000)
    evidence["http_status"] = statuses[-1] if statuses else None
    evidence["result_text"] = page.locator("#result").inner_text() if page.locator("#result").count() else ""
    link = page.locator("#result-content a.btn-download")
    if link.count() and link.is_visible():
        with page.expect_download(timeout=45000) as download:
            link.click()
        download.value.save_as(output)
        with fitz.open(output) as translated:
            evidence["pages"] = [p.get_text() for p in translated]
        evidence["page_count"] = len(evidence["pages"])
        evidence["source_markers_by_page"] = [i + 1 for i, text in enumerate(evidence["pages"]) if "SOURCE-PAGE-" in text]
    evidence["page_errors"] = errors
    page.screenshot(path=str(OUT / "id1-live-spanish-output-probe.png"))
    context.close()
    browser.close()

source.unlink(missing_ok=True)
(OUT / "browser-live-id1-spanish-output-probe.json").write_text(
    json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(evidence, ensure_ascii=False, indent=2))
