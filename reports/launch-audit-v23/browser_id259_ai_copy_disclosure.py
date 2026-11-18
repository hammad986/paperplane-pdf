from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id259-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        pdf = fitz.open()
        for i in range(10):
            pdf.new_page().insert_text((72, 72), f"Original report page {i + 1}")
        source = pdf.tobytes()
        pdf.close()
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no, width in ((1, 1366), (2, 390)):
                page = browser.new_page(viewport={"width": width, "height": 844})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/ai-intelligence", wait_until="networkidle")
                page.locator("#ai-file-input").set_input_files({
                    "name": "original-report.pdf", "mimeType": "application/pdf", "buffer": source
                })
                page.wait_for_function("document.querySelector('#ai-doc-meta')?.textContent.includes('10 pages')", timeout=15000)
                note = page.locator("#ai-doc-source-note")
                assert note.is_visible()
                text = note.inner_text()
                assert "Studio edits are not reflected" in text and "reopen the edited PDF" in text, text
                layout = page.evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,noteWidth:Math.round(document.querySelector('#ai-doc-source-note').getBoundingClientRect().width)})")
                assert layout["width"] == layout["scrollWidth"], layout
                assert not errors, errors
                results.append({"round": round_no, "viewport": width,
                                "ai_page_count": page.locator("#ai-doc-meta").inner_text(),
                                "disclosure": text, "layout": layout, "page_errors": errors})
                page.screenshot(path=str(OUT / f"id259-ai-copy-round{round_no}.png"))
                page.close()
            browser.close()
        (OUT / "browser-id259-ai-copy-disclosure.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
