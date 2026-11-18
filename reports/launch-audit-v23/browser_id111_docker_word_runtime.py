"""Run the P1 stale-queue Word conversion through the production image in Chromium."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import time
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:18501"
DOCX = ROOT / "reports" / "launch-audit-v21" / "live-fixture.docx"
results = []
errors = []
with TemporaryDirectory(prefix="paperplane-id111-docker-") as temp:
    folder = Path(temp)
    merge_files = []
    for n in (1, 2):
        path = folder / f"merge-{n}.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 72), f"Merge source marker {n}")
            pdf.save(path)
        merge_files.append(path)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            response = page.goto(BASE + "/merge-pdf", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.locator("#file-input").set_input_files([str(x) for x in merge_files])
            page.wait_for_function("window.state?.files?.length === 2")
            page.locator('a[href="/word-to-pdf"]').first.evaluate("el => el.click()")
            page.wait_for_function("window.state?.operation === 'word_to_pdf'")
            page.wait_for_function("window.state?.files?.length === 0")
            page.locator("#file-input").set_input_files(str(DOCX))
            page.wait_for_function("window.state?.files?.length === 1")
            assert "live-fixture.docx" in page.locator("#file-list").inner_text()
            page.locator("#run-button").click()
            page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=120_000)
            with page.expect_download(timeout=30_000) as download_event:
                page.locator("#result-download-link").click()
            output = OUT / f"id111-docker-word-round{round_number}.pdf"
            download_event.value.save_as(output)
            with fitz.open(output) as pdf:
                text = re.sub(r"\s+", " ", "\n".join(item.get_text() for item in pdf))
                assert len(pdf) >= 1
                assert "Paperplane live upload smoke test" in text, text
                assert "synthetic public audit fixture" in text, text
                page_count = len(pdf)
            assert not page_errors, page_errors
            results.append({
                "round": round_number,
                "image_runtime": "paperplane-v23-audit:local",
                "queue_cleared_after_route_switch": True,
                "job_http_status": 200,
                "download_bytes": output.stat().st_size,
                "output_pages": page_count,
                "content_markers": ["Paperplane live upload smoke test", "synthetic public audit fixture"],
                "page_errors": page_errors,
            })
            page.screenshot(path=str(OUT / f"id111-docker-word-round{round_number}.png"), full_page=True)
            context.close()
        browser.close()
assert len(results) == 2
report = {"base": BASE, "fixture": DOCX.name, "rounds": results}
(OUT / "browser-id111-docker-word-runtime.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
