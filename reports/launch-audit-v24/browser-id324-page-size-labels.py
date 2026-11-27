"""Verify Studio labels use each page's actual CropBox dimensions."""
from __future__ import annotations

import base64
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id324-page-size-labels.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id324-") as temp_name:
        temp = Path(temp_name)
        source = temp / "id324-letter-and-crop.pdf"
        with fitz.open() as document:
            letter = document.new_page(width=612, height=792)
            letter.insert_text((60, 90), "ID324 US Letter page")
            cropped = document.new_page(width=612, height=792)
            cropped.set_cropbox(fitz.Rect(20, 30, 560, 750))
            cropped.insert_text((60, 90), "ID324 cropped page")
            document.save(source)
        app, base, _identities = helper.start_server(temp / "data")
        evidence = {"page_errors": [], "console_errors": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                page.goto(base + "/rotate-pdf", wait_until="domcontentloaded")
                source_b64 = base64.b64encode(source.read_bytes()).decode("ascii")
                page.evaluate("""b64 => {
                  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                  const blob = new Blob([bytes], {type: 'application/pdf'});
                  window.showDownloadResult({output_name: 'id324-fixture.pdf', output_size: blob.size, page_count: 2}, URL.createObjectURL(blob), {blob});
                }""", source_b64)
                page.locator("#result-view-studio-btn").click()
                page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount === 2")
                cards = page.locator("#studio-thumbnails-container .organizer-thumb-card")
                cards.nth(0).scroll_into_view_if_needed()
                page.wait_for_function("document.querySelector('#studio-thumbnails-container .organizer-thumb-card[data-page=\"1\"] .thumb-meta-text')?.textContent?.includes('612×792pt')")
                cards.nth(1).scroll_into_view_if_needed()
                page.wait_for_function("document.querySelector('#studio-thumbnails-container .organizer-thumb-card[data-page=\"2\"] .thumb-meta-text')?.textContent?.includes('540×720pt')")
                evidence["page_sizes"] = [card.locator(".thumb-meta-text").inner_text() for card in cards.all()]
                evidence["pages"] = page.locator("#studio-thumbnails-container .organizer-thumb-card").count()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("pages") == 2
            and evidence.get("page_sizes") == ["612×792pt", "540×720pt"]
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
