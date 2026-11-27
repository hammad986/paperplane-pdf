from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id353-") as temp:
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
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base + "/sign-pdf", wait_until="domcontentloaded", timeout=20000)
                heading = page.locator("#seo-page-heading").inner_text()
                body = page.locator("body").inner_text()
                seo_response = page.request.get(base + "/api/seo/sign")
                seo = seo_response.json()
                catalog = page.request.get(base + "/api/operations").json()
                signature_entry = catalog["sign"]
                evidence.update({"http_status": response.status if response else None,
                                 "heading": heading, "page_title": page.title(),
                                 "intro_visible": "does not verify the signer’s identity" in body,
                                 "warning_visible": "not identity verification" in body,
                                 "catalog_label": signature_entry.get("label"),
                                 "catalog_description": signature_entry.get("description"),
                                 "seo_title": seo.get("title"), "seo_how_to": seo.get("how_to"),
                                 "seo_faqs": seo.get("faqs")})
                directory_response = page.goto(base + "/tool-desk", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_function("document.querySelector('#tool-desk-tools-catalog')?.innerText.includes('Signature Stamp')", timeout=15000)
                evidence["directory_http_status"] = directory_response.status if directory_response else None
                evidence["directory_signature_stamp_visible"] = page.get_by_text("Signature Stamp", exact=True).count() > 0
                page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id353-signature-stamp-label.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = (evidence.get("http_status") == 200
                           and evidence.get("heading") == "Add a visual signature stamp"
                           and evidence.get("intro_visible") and evidence.get("warning_visible")
                           and evidence.get("directory_http_status") == 200
                           and evidence.get("directory_signature_stamp_visible")
                           and evidence.get("catalog_label") == "Signature Stamp"
                           and "Visual Signature Stamp" in evidence.get("seo_title", "")
                           and not evidence["page_errors"] and not evidence["console_errors"])
    output = ROOT / "reports" / "launch-audit-v24" / "browser-id353-signature-stamp-label.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
