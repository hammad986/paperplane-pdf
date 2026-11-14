"""Exercise the reported 60 MiB / 759+10-page merge through local Chromium."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).parent
V14_SCRIPT = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("paperplane_v14_browser_helpers", V14_SCRIPT)
helpers = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(helpers)


def create_realistic_large_pdf(path: Path, temp: Path) -> dict:
    # Build large scanned-page resources instead of hiding bytes in an
    # attachment. Each unique raster is used on multiple pages, like a long
    # scanned packet with recurring full-page source images.
    image_paths = []
    for index in range(20):
        image_path = temp / f"scan-{index:02}.jpg"
        image = Image.frombytes("RGB", (2048, 2048), os.urandom(2048 * 2048 * 3))
        image.save(image_path, "JPEG", quality=88, optimize=False)
        image.close()
        image_paths.append(image_path)

    with fitz.open() as pdf:
        xrefs = []
        for image_path in image_paths:
            page = pdf.new_page(width=612, height=792)
            xrefs.append(page.insert_image(page.rect, filename=str(image_path)))
            page.insert_text((18, 24), f"SCANNED PACKET PAGE {len(pdf)}")
        for index in range(759 - len(xrefs)):
            page_number = len(pdf) + 1
            page = pdf.new_page(width=612, height=792)
            xref = xrefs[index % len(xrefs)]
            page.insert_image(page.rect, xref=xref)
            page.insert_text((18, 24), f"SCANNED PACKET PAGE {page_number}")
        pdf.save(path, garbage=3, deflate=True)

    ten_page = temp / "ten-pages.pdf"
    with fitz.open() as pdf:
        for number in range(1, 11):
            pdf.new_page().insert_text((72, 72), f"SECOND DOCUMENT PAGE {number}")
        pdf.save(ten_page)
    with fitz.open(path) as pdf:
        return {"input_bytes": path.stat().st_size, "input_pages": pdf.page_count,
                "second_document_pages": 10}


def run_round(browser, number: int) -> dict:
    started = time.time()
    with TemporaryDirectory(prefix=f"paperplane-v15-merge-{number}-") as temp_dir:
        temp = Path(temp_dir)
        large = temp / "scanned-760-page.pdf"
        small = temp / "ten-pages.pdf"
        fixtures = create_realistic_large_pdf(large, temp)
        if fixtures["input_bytes"] < 50 * 1024 * 1024:
            raise AssertionError(f"Real page resources produced only {fixtures['input_bytes']} bytes")
        if fixtures["input_pages"] != 759:
            raise AssertionError(fixtures)

        app, base, identity = helpers.start_server(temp)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page_errors = []
        jobs = []
        page.on("pageerror", lambda error: page_errors.append(str(error).splitlines()[0][:180]))
        page.on("request", lambda request: jobs.append(request.url)
                 if request.method == "POST" and urlsplit(request.url).path == "/api/jobs" else None)
        try:
            port = int(urlsplit(base).port)
            for _ in range(80):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local server exited before large merge test")
                    time.sleep(0.15)
            page.context.add_cookies([{"name": "paperplane_token", "value": identity["accounts"][0][1],
                                      "url": base, "httpOnly": True}])
            response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
            assert response and response.status == 200
            page.locator("#client-privacy-toggle").wait_for(state="attached")
            if page.locator("#client-privacy-toggle").is_checked():
                page.locator("#client-privacy-toggle").evaluate(
                    "el => { el.checked = false; el.dispatchEvent(new Event('change', { bubbles: true })); }"
                )
            page.locator("#file-input").set_input_files([str(large), str(small)])
            page.locator(".file-row-card").nth(1).wait_for(state="visible", timeout=15000)
            page.locator("#run-button").click()
            page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=840000)
            with page.expect_download(timeout=180000) as event:
                page.locator("#result-download-link").click()
            output = temp / "merged-769-pages.pdf"
            event.value.save_as(output)
            with fitz.open(output) as pdf:
                assert len(pdf) == 769, f"Expected 769 pages, received {len(pdf)}"
                first = pdf[0].get_text()
                last_large = pdf[758].get_text()
                first_small = pdf[759].get_text()
                last_small = pdf[768].get_text()
                assert "SCANNED PACKET PAGE 1" in first
                assert "SCANNED PACKET PAGE 759" in last_large
                assert "SECOND DOCUMENT PAGE 1" in first_small
                assert "SECOND DOCUMENT PAGE 10" in last_small
            assert len(jobs) == 1, f"Expected one server job, observed {len(jobs)}"
            assert not page_errors, page_errors
            return {**fixtures, "round": number, "output_bytes": output.stat().st_size,
                    "output_pages": 769, "content_markers": 4, "server_job_posts": len(jobs),
                    "page_errors": page_errors, "duration_seconds": round(time.time() - started, 2)}
        finally:
            context.close()
            app.terminate()
            app.wait(timeout=15)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        results = []
        for round_number in (1, 2):
            results.append(run_round(browser, round_number))
            REPORT.mkdir(parents=True, exist_ok=True)
            (REPORT / "browser-large-merge.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(results[-1], indent=2), flush=True)
        browser.close()
