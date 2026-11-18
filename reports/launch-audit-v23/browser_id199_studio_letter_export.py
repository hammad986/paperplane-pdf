"""Verify Studio A4-to-Letter resize survives the actual Export PDF download."""
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import fitz
import json
import time
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:18501"
results = []
with TemporaryDirectory(prefix="paperplane-id199-") as temp:
    source = Path(temp) / "a4-source.pdf"
    with fitz.open() as document:
        page = document.new_page(width=595.28, height=841.89)
        page.insert_text((72, 72), "ID199 A4 TO LETTER EXPORT MARKER")
        document.save(source)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = page.goto(BASE + "/studio", wait_until="domcontentloaded")
            assert response and response.status == 200
            login = page.request.post(BASE + "/api/auth/login", data={"email": "audit-id199@example.com", "password": "Dummy-Password-Only-2026!"}, headers={"content-type": "application/json"})
            assert login.status == 200, login.text()
            page.reload(wait_until="domcontentloaded")
            page.locator("#tab-studio-view").click()
            page.wait_for_function("document.querySelector('#view-pdf-studio') && !document.querySelector('#view-pdf-studio').hidden")
            page.locator("#studio-file-input").set_input_files(str(source))
            page.wait_for_function("window.state?.studio?.pageCount === 1 || window.state?.studio?.pdfDoc", timeout=30000)
            page.wait_for_function("document.querySelector('#studio-page-count')?.textContent.trim() === '1'", timeout=30000)
            page.locator("#btn-mode-organize").click()
            page.locator(".organizer-thumb-card .thumb-checkbox").first.check()
            page.locator("#organizer-batch-bar:not([hidden])").wait_for(state="visible")
            page.locator("#batch-resize-btn").click()
            page.locator("#page-resize-modal:not([hidden])").wait_for(state="visible")
            page.locator("#resize-preset-select").select_option("Letter")
            page.locator("#resize-scope-all").check() if page.locator("#resize-scope-all").count() else page.locator('input[name="resize-scope"][value="all"]').check()
            page.locator("#btn-apply-resize").click()
            page.locator("#page-resize-modal").wait_for(state="hidden")
            page.wait_for_function("document.body.innerText.includes('Pages resized successfully.')", timeout=30000)
            resized_encoded = page.evaluate("""async () => {
              const bytes = new Uint8Array(await window.PaperplanePageOrganizer.sourceFile.arrayBuffer());
              let binary = ''; for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
              return btoa(binary);
            }""")
            resized_bytes = base64.b64decode(resized_encoded)
            with fitz.open(stream=resized_bytes, filetype="pdf") as resized_pdf:
                resized_width, resized_height = resized_pdf[0].rect.width, resized_pdf[0].rect.height
            with page.expect_download(timeout=60000) as event:
                page.locator("#save-studio-btn").click()
            download = event.value
            target = OUT / f"id199-letter-export-round{round_number}.pdf"
            download.save_as(target)
            with fitz.open(target) as exported:
                assert len(exported) == 1
                width, height = exported[0].rect.width, exported[0].rect.height
                text = exported[0].get_text()
                assert abs(width - 612) < 1 and abs(height - 792) < 1, (width, height)
                assert "ID199 A4 TO LETTER EXPORT MARKER" in text, text
            assert not errors, errors
            results.append({"round": round_number, "resize_width_points": resized_width, "resize_height_points": resized_height, "export_http_status": 200, "output_pages": 1, "width_points": width, "height_points": height, "marker_retained": True, "download_bytes": target.stat().st_size, "page_errors": errors})
            context.close()
        browser.close()
report = {"fixture": "synthetic one-page A4 PDF", "target": "US Letter 612 × 792 pt", "rounds": results}
assert len(results) == 2
(OUT / "browser-id199-studio-letter-export.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
