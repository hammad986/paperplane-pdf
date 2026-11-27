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
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    source = ROOT / "reports" / "launch-audit-v24" / "fixtures" / "arxiv-1706.03762v7.pdf"
    with fitz.open(source) as pdf:
        source_pages, source_text = pdf.page_count, sum(len(page.get_text()) for page in pdf)
    source_bytes = source.stat().st_size
    with TemporaryDirectory(prefix="paperplane-v24-id346-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for round_no in (1, 2):
                    response = page.goto(f"{base}/convert-pdf-to-grayscale", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    notice = page.locator("#options")
                    assert "text may lose searchability" in notice.inner_text()
                    assert page.get_by_role("link", name="run OCR PDF").is_visible()
                    page.locator("#file-input").set_input_files(str(source))
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=120000)
                    metadata = page.locator("#result-meta").inner_text()
                    assert "rasterized at 150 DPI" in metadata and "searchable text" in metadata
                    with page.expect_download(timeout=60000) as event:
                        page.locator("#result-download-link").click()
                    target = ROOT / "reports" / "launch-audit-v24" / f"id346-arxiv-grayscale-round{round_no}.pdf"
                    event.value.save_as(target)
                    with fitz.open(target) as output:
                        assert output.page_count == source_pages
                        remaining_text = sum(len(item.get_text()) for item in output)
                        assert remaining_text == 0, remaining_text
                        assert all(item.get_images(full=True) for item in output)
                    evidence["rounds"].append({"round": round_no, "source_pages": source_pages,
                        "source_bytes": source_bytes, "source_text_chars": source_text,
                        "output_bytes": target.stat().st_size, "output_pages": source_pages,
                        "output_size_may_increase_or_decrease": True,
                        "output_text_chars": remaining_text, "all_pages_image_based": True,
                        "ui_warns_about_rasterization_and_searchability": True,
                        "ocr_recovery_link_visible": True, "result_warning": metadata})
                    if round_no == 1:
                        page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id346-grayscale-warning.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 2 and not evidence["page_errors"] and not evidence["console_errors"]
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id346-grayscale-tradeoff.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
