from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
PDF = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"


doc = fitz.open(PDF)
pdf_check = {
    "path": str(PDF),
    "pages": doc.page_count,
    "bytes": PDF.stat().st_size,
    "first_page_text": doc[0].get_text()[:240],
}
assert doc.page_count == 69
assert "Page 1" in pdf_check["first_page_text"]
doc.close()

result: dict[str, object] = {
    "base": BASE,
    "pdf_check": pdf_check,
    "viewports": [],
    "page_errors": [],
    "console_errors": [],
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    result["chromium_version"] = browser.version
    for width, height, mobile in ((375, 812, True), (1104, 860, False)):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            is_mobile=mobile,
            has_touch=mobile,
        )
        page = context.new_page()
        page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
        page.on(
            "console",
            lambda message: result["console_errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        started = time.monotonic()
        response = page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
        page.locator("#tool-title").wait_for(state="visible", timeout=30000)
        page.screenshot(path=str(OUT / f"phase0-before-{width}.png"), full_page=True)
        viewport_result = {
            "width": width,
            "height": height,
            "http_status": response.status if response else None,
            "title": page.locator("#tool-title").inner_text().strip(),
            "document_width": page.evaluate("document.documentElement.scrollWidth"),
            "body_width": page.evaluate("document.body.scrollWidth"),
            "load_seconds": round(time.monotonic() - started, 3),
        }
        assert viewport_result["http_status"] == 200
        assert viewport_result["title"] == "Merge PDF"
        assert viewport_result["document_width"] == width
        result["viewports"].append(viewport_result)
        context.close()
    browser.close()

assert result["page_errors"] == []
assert result["console_errors"] == []
(OUT / "phase0-smoke.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(json.dumps(result, indent=2, ensure_ascii=False))
