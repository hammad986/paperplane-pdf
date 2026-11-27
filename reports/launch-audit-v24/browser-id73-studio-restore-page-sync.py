"""Check Studio pager and selected page remain aligned after reloading."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

output = Path(__file__).resolve().parent / "browser-id73-studio-restore-page-sync.json"
rounds: list[dict[str, object]] = []
errors: list[str] = []
with tempfile.TemporaryDirectory(prefix="paperplane-id73-") as temp_name:
    temp = Path(temp_name)
    source = temp / "restore-page-sync.pdf"
    with fitz.open() as document:
        for number in range(1, 6):
            document.new_page().insert_text((72, 72), f"Page {number} restore marker RST{number:02d}")
        document.save(source)
    app, base, _identity = helper.start_server(temp / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for attempt in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '5' && !document.querySelector('#page-jump-input')?.disabled", timeout=20_000)
                for target in (2, 3, 4):
                    page.locator("#next-page-btn").click()
                    page.wait_for_function("n => document.querySelector('#page-jump-input')?.value === String(n)", arg=target, timeout=10_000)
                page.wait_for_function("document.querySelector('#page-jump-input')?.value === '4'", timeout=10_000)
                before = page.evaluate("""async () => {
                  const canvas = document.querySelector('#studio-page-stack .studio-page-sheet[data-page="4"] .pdf-page-canvas');
                  const doc = window.state?.studio?.pdfDoc;
                  const content = doc && await (await doc.getPage(4)).getTextContent();
                  return { pager: document.querySelector('#page-jump-input')?.value,
                    pageCount: doc?.numPages || 0, currentPage: window.state?.studio?.currentPage || 0,
                    canvasRendered: canvas?.dataset.rendered === 'true',
                    pageText: content?.items.map(item => item.str).join(' ') || '' };
                }""")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '5'", timeout=30_000)
                page.wait_for_function("document.querySelector('#page-jump-input')?.value === '4'", timeout=20_000)
                page.wait_for_function("document.querySelector('#studio-page-stack .studio-page-sheet[data-page=\"4\"] .pdf-page-canvas')?.dataset.rendered === 'true'", timeout=20_000)
                after = page.evaluate("""async () => {
                  const canvas = document.querySelector('#studio-page-stack .studio-page-sheet[data-page="4"] .pdf-page-canvas');
                  const doc = window.state?.studio?.pdfDoc;
                  const content = doc && await (await doc.getPage(4)).getTextContent();
                  return { pager: document.querySelector('#page-jump-input')?.value,
                    pageCount: doc?.numPages || 0, currentPage: window.state?.studio?.currentPage || 0,
                    canvasRendered: canvas?.dataset.rendered === 'true',
                    pageText: content?.items.map(item => item.str).join(' ') || '' };
                }""")
                rounds.append({"round": attempt, "before_reload": before, "after_reload": after})
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)
result = {
    "build": "app.js?v=191, styles.css?v=70",
    "rounds": rounds,
    "page_errors": errors,
    "passed": len(rounds) == 2 and all(row["before_reload"]["pager"] == "4" and row["before_reload"]["currentPage"] == 4 and row["before_reload"]["pageCount"] == 5 and row["before_reload"]["canvasRendered"] and "RST04" in row["before_reload"]["pageText"] and row["after_reload"]["pager"] == "4" and row["after_reload"]["currentPage"] == 4 and row["after_reload"]["pageCount"] == 5 and row["after_reload"]["canvasRendered"] and "RST04" in row["after_reload"]["pageText"] for row in rounds) and not errors,
}
output.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
