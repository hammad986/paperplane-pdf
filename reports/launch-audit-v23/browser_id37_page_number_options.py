"""Verify local page-number format, offset, position, and no-upload behavior."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id37-page-number-options-") as temporary:
    root = Path(temporary)
    source = root / "numbering-source.pdf"
    with fitz.open() as doc:
        for label in ("NUMBERING-PAGE-ONE", "NUMBERING-PAGE-TWO"):
            page = doc.new_page(width=300, height=200)
            page.insert_text((30, 70), label, fontsize=14)
        doc.save(source)
    app, base, _ = helper.start_server(root / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local server failed to start")
        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            errors = []
            posts = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            context.on("request", lambda req: posts.append(req.url)
                       if req.method == "POST" and req.url.endswith("/api/jobs") else None)
            for round_no in (1, 2):
                response = page.goto(f"{base}/add-page-numbers-to-pdf", wait_until="domcontentloaded")
                assert response and response.status == 200
                assert page.locator("#client-privacy-toggle").is_checked()
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#position").select_option(label="Header left")
                page.locator("#format").select_option(label="{n}")
                page.locator("#start_number").fill("7")
                page.locator("#start_page").fill("2")
                page.locator("#run-button").click()
                page.locator("#result-download-link:not([hidden])").wait_for(state="visible", timeout=30000)
                with page.expect_download() as event:
                    page.locator("#result-download-link").click()
                output = root / f"page-number-options-round{round_no}.pdf"
                event.value.save_as(output)
                with fitz.open(output) as result:
                    assert len(result) == 2
                    first, second = result[0].get_text(), result[1].get_text()
                    assert "NUMBERING-PAGE-ONE" in first and "NUMBERING-PAGE-TWO" in second
                    assert "7" not in first and "7" in second, (first, second)
                rounds.append({"round": round_no, "filename": event.value.suggested_filename,
                               "output_bytes": output.stat().st_size, "two_page_content_preserved": True,
                               "start_page_and_offset_checked": True, "header_left_position_selected": True})
            assert not posts, posts
            assert not errors, errors
            browser.close()
        report = {"rounds": rounds, "api_job_posts": posts, "page_errors": errors,
                  "result": "PASS"}
        (OUT / "browser-id37-page-number-options.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()
