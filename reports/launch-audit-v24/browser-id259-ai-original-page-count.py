"""Check that AI explicitly distinguishes an original PDF from Studio page edits."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    evidence = {"page_errors": [], "console_errors": [], "rounds": []}
    with TemporaryDirectory(prefix="paperplane-v24-id259-") as name:
        temp = Path(name)
        fixture = temp / "ten-pages.pdf"
        with fitz.open() as pdf:
            for number in range(1, 11):
                pdf.new_page().insert_text((72, 72), f"ID 259 source marker page {number}")
            pdf.save(fixture)
        app, base, _ = helper.start_server(temp / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                response = page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                page.locator("#ai-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#ai-doc-meta')?.textContent.includes('10 pages')", timeout=30000)
                page.locator("#ai-open-studio-btn").click()
                page.wait_for_function("!document.querySelector('#view-pdf-studio').hidden", timeout=20000)
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10'", timeout=45000)
                page.wait_for_function("document.querySelector('.pdf-page-canvas[data-rendered=true]')?.width > 1", timeout=20000)
                page.locator("#editor-delete-page-btn").click()
                dialog = page.locator("dialog.app-confirm-dialog")
                dialog.wait_for(state="visible", timeout=5000)
                dialog.locator(".app-confirm-accept").click()
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '9'", timeout=45000)
                studio_pages = page.locator("#page-total-indicator").inner_text()
                page.locator("#tab-ai-view").click()
                page.wait_for_function("!document.querySelector('#view-ai-studio').hidden", timeout=20000)
                page.wait_for_function(
                    "document.querySelector('#ai-doc-meta')?.textContent.includes('AI copy: 10 pages · Studio copy: 9 pages')",
                    timeout=30000,
                )
                meta = page.locator("#ai-doc-meta").inner_text()
                page.screenshot(path=str(OUT / "browser-id259-ai-original-page-count.png"), full_page=True)
                evidence["rounds"].append({
                    "http_status": response.status if response else None,
                    "studio_page_count": studio_pages,
                    "ai_document_meta": meta,
                    "ai_copy_count_disclosed": "AI copy: 10 pages" in meta,
                    "studio_copy_count_disclosed": "Studio copy: 9 pages" in meta,
                })
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except Exception:
                app.kill()
                app.wait(timeout=5)

    evidence["passed"] = (
        len(evidence["rounds"]) == 1
        and evidence["rounds"][0]["http_status"] == 200
        and evidence["rounds"][0]["ai_copy_count_disclosed"]
        and evidence["rounds"][0]["studio_copy_count_disclosed"]
        and not evidence["page_errors"]
        and not evidence["console_errors"]
    )
    (OUT / "browser-id259-ai-original-page-count.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
