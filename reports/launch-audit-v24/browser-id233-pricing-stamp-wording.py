"""Check the current rendered Pricing copy for the reported obsolete label."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    evidence = {"viewports": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id233-") as temp_name:
        app, base, _identity = helper.start_server(Path(temp_name) / "data")
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
                page = browser.new_page()
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for width, height in ((390, 844), (1366, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    response = page.goto(base + "/pricing", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    page.wait_for_function("document.querySelector('#pricing-page-content')?.innerText.trim().length > 0", timeout=15000)
                    body_text = page.locator("#pricing-page-content").inner_text()
                    assert "Shop Stamp" not in body_text, {"width": width, "copy": body_text}
                    assert "Document Stamps & Watermarks" in body_text, {"width": width, "copy": body_text}
                    evidence["viewports"].append({
                        "width": width,
                        "obsolete_label_absent": True,
                        "current_label_visible": True,
                    })
                    page.screenshot(path=str(OUT / f"browser-id233-pricing-stamp-wording-{width}.png"), full_page=True)
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)
    evidence["result"] = "passed"
    (OUT / "browser-id233-pricing-stamp-wording.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
