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


def make_fixture(path: Path) -> None:
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 50), "Heading From Source", fontsize=22)
        page.insert_text((60, 80), "Section One: Report Findings", fontsize=16)
        page.insert_text((60, 110), "Regular descriptive paragraph.", fontsize=10)
        page.insert_text((60, 130), "- - Normalize the broken bullet.", fontsize=10)
        for point, text in (((70, 190), "Item"), ((220, 190), "Amount"),
                            ((70, 220), "Revenue"), ((220, 220), "12%")):
            page.insert_text(point, text, fontsize=10)
        shape = page.new_shape()
        for start, end in (((60, 170), (320, 170)), ((60, 200), (320, 200)),
                           ((60, 230), (320, 230)), ((60, 170), (60, 230)),
                           ((190, 170), (190, 230)), ((320, 170), (320, 230))):
            shape.draw_line(start, end)
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()
        pdf.save(path)


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id336-") as temp:
        root = Path(temp)
        fixture_path = root / "structure-test.pdf"
        make_fixture(fixture_path)
        app, base, _ = helper.start_server(root / "data")
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
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for round_no in (1, 2):
                    page.goto(base + "/pdf-to-markdown", wait_until="domcontentloaded", timeout=20000)
                    page.locator("#file-input").set_input_files(str(fixture_path))
                    page.locator("#run-button").click()
                    page.wait_for_function("document.querySelector('#result-download-link') && !document.querySelector('#result-download-link').hidden", timeout=60000)
                    with page.expect_download(timeout=30000) as info:
                        page.locator("#result-download-link").click()
                    target = root / f"round-{round_no}.md"
                    info.value.save_as(target)
                    markdown = target.read_text(encoding="utf-8")
                    warning = page.locator("#result-meta").inner_text()
                    checks = {
                        "document_title_heading": "# Heading From Source" in markdown,
                        "section_heading": "## Section One: Report Findings" in markdown,
                        "single_bullet_marker": "- Normalize the broken bullet." in markdown,
                        "no_doubled_bullet": "- - Normalize" not in markdown,
                        "browser_discloses_table_limit": "tables, math layout, and scanned text are not reconstructed" in warning,
                    }
                    evidence["rounds"].append({"round": round_no, "markdown_bytes": target.stat().st_size,
                                               "checks": checks, "result_warning": warning,
                                               "markdown_excerpt": markdown[:900]})
                    if round_no == 1:
                        page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id336-markdown-structure.png"), full_page=True)

                for round_no in (1, 2):
                    response = context.request.post(base + "/api/jobs", multipart={
                        "operation": "pdf_to_markdown", "options": "{}",
                        "files": {"name": "structure-test.pdf", "mimeType": "application/pdf", "buffer": fixture_path.read_bytes()},
                    })
                    if response.status != 202:
                        raise AssertionError(f"Server Markdown job submission failed: {response.status} {response.text()}")
                    job_id = response.json()["job_id"]
                    for _ in range(300):
                        status_response = context.request.get(base + f"/api/jobs/{job_id}")
                        status = status_response.json()
                        if status.get("status") in {"completed", "failed"}:
                            break
                        time.sleep(0.1)
                    if status.get("status") != "completed":
                        raise AssertionError(f"Server Markdown job failed: {status}")
                    download_response = context.request.get(base + f"/api/jobs/{job_id}/download")
                    if download_response.status != 200:
                        raise AssertionError(f"Server Markdown download failed: {download_response.status}")
                    markdown = download_response.body().decode("utf-8")
                    checks = {
                        "document_title_heading": "# structure-test" in markdown,
                        "section_heading": "## Section One: Report Findings" in markdown,
                        "single_bullet_marker": "- Normalize the broken bullet." in markdown,
                        "no_doubled_bullet": "- - Normalize" not in markdown,
                        "table_header": "| Item | Amount |" in markdown,
                        "table_data": "| Revenue | 12% |" in markdown,
                        "table_separator": "| --- | --- |" in markdown,
                    }
                    evidence.setdefault("server_rounds", []).append({"round": round_no,
                        "markdown_bytes": len(download_response.body()), "checks": checks,
                        "markdown_excerpt": markdown[:900]})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = (len(evidence["rounds"]) == 2
                           and all(all(item["checks"].values()) for item in evidence["rounds"])
                           and len(evidence.get("server_rounds", [])) == 2
                           and all(all(item["checks"].values()) for item in evidence.get("server_rounds", []))
                           and not evidence["page_errors"] and not evidence["console_errors"])
    output = ROOT / "reports" / "launch-audit-v24" / "browser-id336-markdown-structure.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
