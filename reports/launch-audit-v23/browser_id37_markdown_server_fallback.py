"""Approve the explicit local server fallback for real 69-page PDF-to-Markdown."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path(r"C:/Users/mdham/Downloads/notes.pdf")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with fitz.open(SOURCE) as pdf:
    expected_pages = [page.get_text() for page in pdf]
assert len(expected_pages) == 69

def words(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"[\w]+", normalized, flags=re.UNICODE)

base = os.environ.get("PAPERPLANE_TEST_BASE")
app = None
with TemporaryDirectory(prefix="paperplane-id37-markdown-consented-") as temporary:
    if not base:
        app, base, _ = helper.start_server(Path(temporary) / "data")
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
                context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'local')")
                page = context.new_page()
                errors = []
                posts = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: posts.append(request.url)
                        if request.method == "POST" and "/api/jobs" in request.url else None)
                response = page.goto(base + "/?tool=pdf_to_markdown", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#file-input").set_input_files(str(SOURCE))
                page.locator("#run-button").click()
                dialog = page.locator(".app-confirm-dialog")
                dialog.wait_for(state="visible", timeout=90000)
                prompt = dialog.inner_text()
                assert "math or custom-font glyphs" in prompt, prompt
                assert "temporary server processing" in prompt, prompt
                assert "Upload and retry" in prompt, prompt
                with page.expect_response(lambda r: "/api/jobs" in r.url and r.request.method == "POST", timeout=30000) as job_event:
                    page.locator(".app-confirm-accept").click()
                job_response = job_event.value
                assert job_response.status == 202, (job_response.status, job_response.text())
                job_id = job_response.json().get("job_id")
                page.locator("#result:not([hidden])").wait_for(state="visible", timeout=180000)
                assert page.locator("#result-download-link:not([hidden])").is_visible()
                with page.expect_download(timeout=30000) as download_event:
                    page.locator("#result-download-link").click()
                download = download_event.value
                output = OUT / f"id37-consented-markdown-round{number}.md"
                download.save_as(output)
                markdown = output.read_text(encoding="utf-8")
                matches = list(re.finditer(r"^## Page (\d+)\s*$", markdown, flags=re.MULTILINE))
                assert [int(match.group(1)) for match in matches] == list(range(1, 70)), [m.group(1) for m in matches]
                coverage = []
                for index, match in enumerate(matches):
                    start = match.end()
                    end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
                    source_tokens = words(expected_pages[index])
                    output_tokens = set(words(markdown[start:end]))
                    ratio = sum(token in output_tokens for token in source_tokens) / max(1, len(source_tokens))
                    coverage.append(round(ratio, 4))
                assert min(coverage) >= .90, {"minimum": min(coverage), "page": coverage.index(min(coverage)) + 1}
                assert "Introduction to Machine Learning Class Notes" in markdown
                assert "Model Selection" in markdown
                assert job_id and job_id not in markdown
                assert posts == [job_response.url.rsplit("/", 1)[0] + "/jobs"], posts
                assert not errors, errors
                rounds.append({"round": number, "status": response.status, "job_status": job_response.status,
                               "output_name": download.suggested_filename, "output_bytes": output.stat().st_size,
                               "pages": len(matches), "all_page_sections_in_order": True,
                               "minimum_page_token_coverage": min(coverage),
                               "average_page_token_coverage": round(sum(coverage) / len(coverage), 4),
                               "first_and_last_page_markers": True, "job_id_not_leaked": True,
                               "upload_had_explicit_consent": True, "job_posts": len(posts), "page_errors": errors})
                context.close()
            browser.close()
        docker_runtime = bool(os.environ.get("PAPERPLANE_TEST_BASE"))
        evidence = {"base": base, "runtime": "production Docker image" if docker_runtime else "local server",
                    "image_id": subprocess.check_output(["docker", "image", "inspect", "paperplane-v23-audit:codex-current", "--format", "{{.Id}}"], text=True).strip() if docker_runtime else None,
                    "fixture": str(SOURCE), "fixture_pages": 69, "rounds": rounds}
        path = OUT / ("browser-id37-consented-markdown-docker.json" if docker_runtime else "browser-id37-consented-markdown-local.json")
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        if app:
            app.terminate()
            app.wait(timeout=5)
