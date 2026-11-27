"""Verify disclosed text-only browser conversion and server mixed-content DOCX fidelity."""
from __future__ import annotations

import io
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from PIL import Image, ImageDraw
from docx import Document
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def build_fixture(path: Path) -> None:
    image = Image.new("RGB", (500, 260), "#e34b40")
    draw = ImageDraw.Draw(image)
    draw.text((30, 100), "EMBEDDED IMAGE PROOF", fill="white")
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    with fitz.open() as pdf:
        for page_no in range(1, 6):
            page = pdf.new_page(width=595, height=842)
            page.insert_text((42, 42), f"Mixed-PDF-Page-{page_no} editable text", fontsize=12)
            page.insert_text((42, 64), f"Unique detail for page {page_no} remains selectable.", fontsize=10)
            if page_no == 1:
                page.insert_image(fitz.Rect(42, 90, 242, 194), stream=encoded.getvalue())
                for x in (42, 240, 440):
                    page.draw_line((x, 240), (x, 330), color=(0, 0, 0), width=1)
                for y in (240, 270, 300, 330):
                    page.draw_line((42, y), (440, y), color=(0, 0, 0), width=1)
                for x, y, text in ((50, 260, "Item"), (250, 260, "Amount"), (50, 290, "Printer"), (250, 290, "$42"),
                                   (50, 320, "Paper"), (250, 320, "$12")):
                    page.insert_text((x, y), text, fontsize=10)
            if page_no == 3:
                page.insert_image(fitz.Rect(330, 110, 490, 220), stream=encoded.getvalue())
        pdf.save(path)


def docx_facts(path: Path) -> dict:
    document = Document(path)
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    cell_text = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    body = "\n".join(paragraphs + cell_text)
    return {
        "bytes": path.stat().st_size,
        "valid_docx": path.read_bytes().startswith(b"PK"),
        "paragraphs": paragraphs,
        "tables": [[ [cell.text for cell in row.cells] for row in table.rows] for table in document.tables],
        "inline_images": len(document.inline_shapes),
        "page_markers": {f"Mixed-PDF-Page-{n}": f"Mixed-PDF-Page-{n}" in body for n in range(1, 6)},
    }


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id308-") as temp_name:
        temp = Path(temp_name)
        source = temp / "mixed-five-page.pdf"
        build_fixture(source)
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
                raise RuntimeError("Local test server did not start")

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/pdf-to-word", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(source))
                page.wait_for_function("window.state?.files?.length === 1", timeout=30000)
                page.wait_for_function("document.querySelector('#run-button') && !document.querySelector('#run-button').disabled", timeout=15000)

                toggle = page.locator("#client-privacy-toggle")
                assert toggle.is_checked(), "The default should be the browser-local conversion mode."
                assert page.locator("#privacy-mode-label").inner_text().strip() == "Text-only DOCX"
                assert "text-only docx export" in toggle.get_attribute("aria-label").lower()
                capability = page.locator("#pdf-to-word-capability-copy").inner_text()
                assert "text-first" in capability.lower() and "does not retain images" in capability.lower() and "table structure" in capability.lower(), capability
                local_capability = capability
                page.locator("#run-button").click()
                page.locator("#result-download-link").wait_for(state="visible", timeout=120000)
                with page.expect_download(timeout=30000) as event:
                    page.locator("#result-download-link").click()
                local_output = OUT / "id308-text-first-browser.docx"
                event.value.save_as(local_output)
                local_facts = docx_facts(local_output)
                local_text = "\n".join(local_facts["paragraphs"])
                assert local_facts["valid_docx"] and all(f"Mixed-PDF-Page-{n}" in local_text for n in range(1, 6)), local_facts
                assert local_facts["inline_images"] == 0 and local_facts["tables"] == [], local_facts

                page.evaluate("localStorage.setItem('paperplane-pdf-processing-mode', 'server')")
                page.goto(base + "/pdf-to-word", wait_until="domcontentloaded")
                toggle = page.locator("#client-privacy-toggle")
                assert not toggle.is_checked(), "The saved Server Processing preference should be restored on navigation."
                assert page.locator("#privacy-mode-label").inner_text().strip() == "Server DOCX reconstruction"
                assert "pdf-to-word-capability-copy" in (toggle.get_attribute("aria-describedby") or "")
                page.locator("#file-input").set_input_files(str(source))
                page.wait_for_function("window.state?.files?.length === 1", timeout=30000)
                page.wait_for_function("document.querySelector('#run-button') && !document.querySelector('#run-button').disabled", timeout=15000)
                capability = page.locator("#pdf-to-word-capability-copy").inner_text()
                assert "detected tables, and embedded images" in capability.lower(), capability
                page.locator("#run-button").click()
                page.locator("#result-download-link").wait_for(state="visible", timeout=120000)
                with page.expect_download(timeout=30000) as event:
                    page.locator("#result-download-link").click()
                server_output = OUT / "id308-mixed-content-server.docx"
                event.value.save_as(server_output)
                server_facts = docx_facts(server_output)
                assert server_facts["valid_docx"]
                assert all(server_facts["page_markers"].values()), server_facts
                assert server_facts["inline_images"] == 2, server_facts
                assert len(server_facts["tables"]) == 1, server_facts
                table_text = " ".join(cell for row in server_facts["tables"][0] for cell in row)
                assert all(marker in table_text for marker in ("Item", "Amount", "Printer", "$42", "Paper", "$12")), server_facts

                page.screenshot(path=str(OUT / "browser-id308-server-docx.png"), full_page=False)
                evidence["browser_mode_disclosure"] = local_capability
                evidence["browser_mode_label"] = "Text-only DOCX"
                evidence["browser_mode_docx"] = local_facts
                evidence["server_mode_docx"] = server_facts
                evidence["server_mode_label"] = "Server DOCX reconstruction"
                evidence["server_output"] = server_output.name
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id308-pdf-to-word-fidelity.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
