"""Check Merge does not show the obsolete temporary-upload reload warning."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id217-merge-retention-copy.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

OBSOLETE = "Some temporary tool uploads may need to be selected again after reload."


def main():
    with TemporaryDirectory(prefix="paperplane-id217-") as temp_name:
        app, base, _identities = helper.start_server(Path(temp_name) / "data")
        evidence = {"page_errors": [], "console_errors": [], "snapshots": []}
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.locator("#view-tool-desk").wait_for(state="visible")
                page.wait_for_function("document.querySelector('#tool-title')?.textContent?.includes('Merge')")
                evidence["snapshots"].append(page.locator("#view-tool-desk").inner_text())
                page.reload(wait_until="domcontentloaded")
                page.locator("#view-tool-desk").wait_for(state="visible")
                page.wait_for_function("document.querySelector('#tool-title')?.textContent?.includes('Merge')")
                evidence["snapshots"].append(page.locator("#view-tool-desk").inner_text())
                evidence["upload_present"] = page.locator("#dropzone").is_visible()
                evidence["file_count"] = page.locator("#file-list .file-item").count()
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and len(evidence["snapshots"]) == 2
            and all(OBSOLETE not in snapshot for snapshot in evidence["snapshots"])
            and evidence.get("upload_present") is True
            and evidence.get("file_count") == 0
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({"overall": evidence["overall"], "http_status": evidence.get("http_status"),
                          "obsolete_warning_present": any(OBSOLETE in snapshot for snapshot in evidence["snapshots"]),
                          "upload_present": evidence.get("upload_present"), "file_count": evidence.get("file_count"),
                          "page_errors": evidence["page_errors"], "console_errors": evidence["console_errors"]}, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
