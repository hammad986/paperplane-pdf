"""Check server-rendered workflow guidance in a real local Chromium browser."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("seo_browser_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

ROUTES = {
    "/": ("Browse the tool directory", "Add the source file", "Review the generated file"),
    "/ocr-pdf": ("Select a scanned PDF", "After selecting the file", "no quality setting is shown"),
    "/html-to-pdf": ("Enter a public web address", "does not offer separate page-size controls", "review its page breaks"),
    "/pdf-to-word": ("text-based PDF", "no OCR settings selector", "Open the DOCX output"),
    "/pdf-to-excel": ("contains tables", "does not show table-region previews", "check row and column alignment"),
    "/pdf-to-ppt": ("pages you want to reuse as slides", "built-in reconstruction behavior", "review text, images, and slide order"),
    "/pdf-to-jpg": ("Select the PDF", "Choose an export resolution", "Download the ZIP"),
    "/excel-to-pdf": ("Select an Excel workbook", "built-in sheet and page-layout", "check the rendered pages"),
    "/scan-to-pdf": ("Select photos or scans", "combined in that sequence", "check page order"),
    "/watermark-pdf": ("Select a PDF", "set opacity", "mark is legible"),
    "/protect-pdf": ("Select the PDF", "Enter the password", "verify it opens"),
    "/pdf-metadata": ("Select the PDF", "title, author, and subject", "check its properties"),
    "/annotate-pdf": ("Select a PDF to annotate", "Choose an annotation type", "reopen it"),
    "/translate-pdf": ("After selecting the PDF", "control is not shown before upload", "Review the translated pages"),
    "/download": ("platform cards", "waitlist form", "browser-based Paperplane tools"),
}


def main() -> None:
    rounds = []
    with helpers.TemporaryDirectory(prefix="paperplane-seo-copy-") as temp:
        app, base, _ = helpers.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local app exited")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local app did not become ready")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for round_no in (1, 2):
                    checked = []
                    errors = []
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    for route, expected in ROUTES.items():
                        response = page.goto(base + route, wait_until="domcontentloaded")
                        assert response and response.status == 200, (route, response.status if response else None)
                        cards = page.locator(".seo-howto-step")
                        assert cards.count() == 3, (route, cards.count())
                        bodies = [text.strip() for text in page.locator(".seo-howto-step p").all_text_contents()]
                        assert len(bodies) == 3 and all(len(body) >= 30 for body in bodies), (route, bodies)
                        combined = " ".join(bodies).lower()
                        for phrase in expected:
                            assert phrase.lower() in combined, (route, phrase, bodies)
                        checked.append({"route": route, "status": response.status, "steps": bodies})
                    assert not errors, errors
                    rounds.append({"round": round_no, "checked_routes": checked, "page_errors": errors})
                    page.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=10)
    output = ROOT / "reports" / "launch-audit-v15" / "browser-seo-workflow-copy.json"
    output.write_text(json.dumps(rounds, indent=2), encoding="utf-8")
    print(json.dumps({"rounds": len(rounds), "routes_per_round": len(ROUTES), "evidence": str(output)}))


if __name__ == "__main__":
    main()
