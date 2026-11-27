from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import socket
import subprocess
import sys
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id37-local-markdown-") as temp:
    root = Path(temp)
    source = root / "structured-markdown.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.insert_text((60, 70), "Browser Markdown Heading", fontsize=22)
        page.insert_text((60, 105), "Plain paragraph remains searchable.", fontsize=10)
        page.insert_text((60, 135), "- - Normalize the broken bullet.", fontsize=10)
        pdf.set_metadata({"title": "Browser Markdown Fixture"})
        pdf.save(source)

    base = os.environ.get("PAPERPLANE_TEST_BASE")
    app = None
    if not base:
        app, base, _ = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)

        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'local')")
                page = context.new_page()
                errors = []
                job_posts = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: job_posts.append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                page.goto(base + "/?tool=pdf_to_markdown", wait_until="domcontentloaded")
                page.locator("#file-input").set_input_files(str(source))
                assert page.locator("#client-privacy-toggle").is_checked()
                option_text = page.locator("#options").inner_text()
                assert "does not reconstruct tables, math layout, or scanned text" in option_text, option_text
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=45000)
                with page.expect_download(timeout=20000) as event:
                    page.locator("#result-download-link").click()
                output_path = root / f"local-markdown-round{number}.md"
                event.value.save_as(output_path)
                markdown = output_path.read_text(encoding="utf-8")
                assert event.value.suggested_filename == "structured-markdown.md", event.value.suggested_filename
                assert "# Browser Markdown Fixture" in markdown, markdown
                assert "# Browser Markdown Heading" in markdown, markdown
                assert "## Page 1" in markdown, markdown
                assert "Plain paragraph remains searchable." in markdown, markdown
                assert "- Normalize the broken bullet." in markdown, markdown
                assert "- - Normalize" not in markdown, markdown
                assert "tables, math layout, and scanned text are not reconstructed" in page.locator("#result-meta").inner_text().lower()
                assert not job_posts, job_posts
                assert not errors, errors
                rounds.append({"round": number, "filename": event.value.suggested_filename,
                               "metadata_title": True, "heading_and_page_structure": True,
                               "paragraph_preserved": True, "bullet_normalized": True,
                               "disclosed_table_and_ocr_limits": True,
                               "job_posts": job_posts, "page_errors": errors})
                context.close()
            browser.close()

        docker_runtime = bool(os.environ.get("PAPERPLANE_TEST_BASE"))
        evidence_name = "browser-id37-local-markdown-docker.json" if docker_runtime else "browser-id37-local-markdown-local.json"
        report = {"base": base, "runtime": "Docker image" if docker_runtime else "local server",
                  "image_id": subprocess.check_output(
                      ["docker", "image", "inspect", "paperplane-v23-audit:codex-current", "--format", "{{.Id}}"],
                      text=True).strip() if docker_runtime else None,
                  "rounds": rounds}
        (OUT / evidence_name).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if app:
            app.terminate()
            app.wait(timeout=5)
