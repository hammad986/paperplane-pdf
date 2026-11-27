"""Measure and content-check a 69-page delete through current local Studio UI."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROUND = os.getenv("PAPERPLANE_ID306_ROUND", "1")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id306-") as temp_name:
        temp = Path(temp_name)
        fixture = temp / "studio-delete-69-pages.pdf"
        with fitz.open() as pdf:
            for page_no in range(1, 70):
                page = pdf.new_page()
                page.insert_text((72, 72), f"ID306 source page marker {page_no:02d}", fontsize=18)
            pdf.save(fixture)

        app, base, _identity = helper.start_server(temp / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Current local Paperplane server did not start")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("window.state?.studio?.pdfDoc?.numPages === 69", timeout=60000)
                page.locator("#btn-mode-organize").click()
                page.locator('.organizer-thumb-card[data-page="34"] .thumb-checkbox').check(force=True)
                page.locator("#batch-delete-btn").click()
                page.locator(".app-confirm-dialog .app-confirm-accept").click(timeout=10000)
                started = time.monotonic()
                page.wait_for_function("window.state.studio.pdfDoc?.numPages === 68", timeout=45000)
                elapsed = time.monotonic() - started
                page.wait_for_function("document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=30000)
                remaining_text = page.evaluate("""async () => {
                  const page = await window.state.studio.pdfDoc.getPage(34);
                  const text = await page.getTextContent();
                  return text.items.map(item => item.str).join(' ');
                }""")
                assert "ID306 source page marker 35" in remaining_text, remaining_text
                evidence.update({
                    "http_build": "current local source",
                    "input_pages": 69,
                    "deleted_page": 34,
                    "remaining_pages": page.evaluate("window.state.studio.pdfDoc.numPages"),
                    "delete_to_reloaded_document_seconds": round(elapsed, 3),
                    "first_content_after_deleted_page": remaining_text,
                    "former_page_35_moved_to_page_34": True,
                })
                assert evidence["remaining_pages"] == 68
                assert elapsed < 10, evidence
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                page.screenshot(path=str(OUT / f"browser-id306-studio-delete-latency-round-{ROUND}.png"), full_page=False)
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / f"browser-id306-studio-delete-latency-round-{ROUND}.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
