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
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": [], "server_job_requests": []}
    with TemporaryDirectory(prefix="paperplane-v24-id163-") as temp:
        work = Path(temp)
        sources = []
        for number in (1, 2):
            path = work / f"private-merge-{number}.pdf"
            with fitz.open() as doc:
                page = doc.new_page()
                page.insert_text((72, 72), f"Private merge marker {number}.")
                doc.save(path)
            sources.append(path)
        app, base, _ = helper.start_server(work / "data")
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
                page = browser.new_page(accept_downloads=True, viewport={"width": 1365, "height": 900}, service_workers="block")
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.on("request", lambda request: evidence["server_job_requests"].append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                for round_no in (1, 2):
                    response = page.goto(f"{base}/merge-pdf", wait_until="domcontentloaded")
                    assert response and response.status == 200
                    toggle = page.locator("#client-privacy-toggle")
                    if not toggle.is_checked():
                        toggle.check()
                    labels = [page.locator(f"#step-{n}").inner_text() for n in range(1, 5)]
                    assert labels == ["1. Prepare Files", "2. Process Pages", "3. Prepare Output", "4. Ready"], labels
                    assert not any("upload" in label.lower() or "stream" in label.lower() for label in labels)
                    page.locator("#file-input").set_input_files([str(path) for path in sources])
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                    with page.expect_download(timeout=15000) as event:
                        page.locator("#result-download-link").click()
                    output = work / f"private-merge-round-{round_no}.pdf"
                    event.value.save_as(output)
                    with fitz.open(output) as result:
                        text = "\n".join(p.get_text() for p in result)
                        assert result.page_count == 2
                        assert "Private merge marker 1." in text and "Private merge marker 2." in text
                    evidence["rounds"].append({"round": round_no, "labels": labels, "local_processing_selected": toggle.is_checked(),
                        "download_pages": 2, "both_page_markers_present": True})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 2 and not evidence["server_job_requests"] and not evidence["page_errors"] and not evidence["console_errors"]
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id163-merge-progress-copy.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
