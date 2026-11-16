"""Content-checked Chromium regression for Scan-to-PDF page-size options."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time

import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
sys.path.insert(0, str(HELPER.parent))
import browser_acceptance_v14 as helper


def main() -> None:
    report_dir = ROOT / "reports" / "launch-audit-v22"
    report_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="paperplane-v22-scan-") as temporary:
        temp = Path(temporary)
        source = temp / "camera-photo.png"
        Image.new("RGB", (1600, 1200), (235, 235, 235)).save(source)
        app, base, _identities = helper.start_server(temp / "server-data")
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start.")
            results = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                layout = []
                for width in (390, 820, 1366, 1920):
                    page.set_viewport_size({"width": width, "height": 900})
                    response = page.goto(f"{base}/scan-to-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.wait_for_timeout(150)
                    measurements = page.evaluate("""() => ({
                      viewport: innerWidth,
                      documentWidth: document.documentElement.scrollWidth,
                      bodyWidth: document.body.scrollWidth,
                      pageSizeOptions: [...document.querySelectorAll('#page_size option')].map(option => option.textContent.trim())
                    })""")
                    assert measurements["documentWidth"] <= width + 2, measurements
                    assert len(measurements["pageSizeOptions"]) == 3, measurements
                    page.screenshot(path=str(report_dir / f"scan-layout-{width}.png"), full_page=True)
                    layout.append(measurements)
                (report_dir / "scan-layout.json").write_text(json.dumps(layout, indent=2), encoding="utf-8")
                for size, expected in (("a4", (841.89, 595.28)), ("letter", (792, 612)), ("original", (576, 432))):
                    response = page.goto(f"{base}/scan-to-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#page_size").select_option(size)
                    page.locator("#run-button").click()
                    page.locator("#result-download-link").wait_for(state="visible", timeout=30000)
                    with page.expect_download(timeout=15000) as download_info:
                        page.locator("#result-download-link").click()
                    download = download_info.value
                    output = report_dir / f"scan-{size}.pdf"
                    download.save_as(output)
                    with fitz.open(output) as pdf:
                        actual = (pdf[0].rect.width, pdf[0].rect.height)
                        assert len(pdf) == 1 and pdf[0].get_images()
                        assert abs(actual[0] - expected[0]) < 1 and abs(actual[1] - expected[1]) < 1
                    results.append({"page_size": size, "download": str(output), "bytes": output.stat().st_size,
                                    "pages": 1, "dimensions_pt": actual})
                assert not page_errors, page_errors
                browser.close()
            (report_dir / "browser-scan-pages.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(results, indent=2))
        finally:
            app.terminate()
            app.wait(timeout=15)


if __name__ == "__main__":
    main()
