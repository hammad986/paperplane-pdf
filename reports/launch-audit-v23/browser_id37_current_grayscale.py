"""Current-source Chromium content check for the server-only Grayscale workflow."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id37-grayscale-") as temporary:
    root = Path(temporary)
    source = root / "colored-source.pdf"
    with fitz.open() as document:
        for page_number, color in ((1, (1, 0, 0)), (2, (0, 0.2, 1))):
            page = document.new_page(width=360, height=480)
            page.insert_text((40, 50), f"ID37-GRAYSCALE-PAGE-{page_number}", fontsize=16, color=color)
            page.draw_rect(fitz.Rect(40, 90, 300, 300), color=color, fill=color)
        document.save(source)

    app, base, _identity = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app did not start")

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number, width in ((1, 1366), (2, 390)):
                context = browser.new_context(viewport={"width": width, "height": 844}, accept_downloads=True)
                page = context.new_page()
                errors: list[str] = []
                job_posts: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)[:300]))
                page.on("request", lambda request: job_posts.append(request.url)
                        if request.method == "POST" and request.url.endswith("/api/jobs") else None)
                response = page.goto(base + "/convert-pdf-to-grayscale", wait_until="domcontentloaded", timeout=15000)
                assert response and response.status == 200
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                with page.expect_download(timeout=20000) as download_wait:
                    page.locator("#result-download-link").click()
                download = download_wait.value
                output = root / f"grayscale-round-{round_number}.pdf"
                download.save_as(output)
                with fitz.open(output) as pdf:
                    assert pdf.page_count == 2
                    channel_diffs = []
                    for pdf_page in pdf:
                        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                        samples = memoryview(pix.samples)
                        for offset in range(0, len(samples), 3):
                            r, g, b = samples[offset:offset + 3]
                            channel_diffs.append(max(r, g, b) - min(r, g, b))
                    max_channel_difference = max(channel_diffs, default=0)
                    assert max_channel_difference <= 2, max_channel_difference
                    grayscale_pixels = len(channel_diffs)
                assert len(job_posts) == 1, job_posts
                assert not errors, errors
                rounds.append({"round": round_number, "viewport": width, "http_status": response.status,
                               "output_bytes": output.stat().st_size, "pages": 2,
                               "grayscale_pixels_checked": grayscale_pixels,
                               "max_rgb_channel_difference": max_channel_difference,
                               "server_job_posts": len(job_posts), "page_errors": errors})
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"operation": "grayscale", "rounds": rounds, "result": "PASS"}
path = OUT / "browser-id37-current-grayscale.json"
path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
