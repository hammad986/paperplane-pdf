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
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id355-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1365, "height": 900})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for round_no in (1, 2):
                    response = page.goto(f"{base}/edit-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    title = page.title()
                    headings = page.locator("h1").all_inner_texts()
                    body = page.locator("body").inner_text()
                    assert title == "Add Text & Stamps | Paperplane", title
                    assert "Add Text & Stamps" in headings, headings
                    assert "Existing PDF text cannot be selected or replaced" in body
                    evidence["rounds"].append({"round": round_no, "http": response.status, "title": title,
                        "tool_heading": "Add Text & Stamps", "existing_text_limitation_disclosed": True})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 2 and not evidence["page_errors"] and not evidence["console_errors"]
    output = ROOT / "reports" / "launch-audit-v24" / "browser-id355-edit-tool-disclosure.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
