"""Content-check 69-page PDF compression in the current production Docker image."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:18502"
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
with fitz.open(SOURCE) as source:
    source_text = [page.get_text() for page in source]
    source_visuals = [page.get_pixmap(matrix=fitz.Matrix(.35, .35), alpha=False) for page in source]
assert len(source_text) == 69
marker = next(line.strip() for line in source_text[0].splitlines() if line.strip())
rounds = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    for round_no in (1, 2):
        context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(BASE + "/compress-pdf", wait_until="domcontentloaded", timeout=30000)
        assert response and response.status == 200
        page.wait_for_function("state.operation==='compress' && document.querySelector('#preset')")
        page.locator("#preset").select_option("100kb")
        page.locator("#file-input").set_input_files(str(SOURCE))
        page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=30000)
        page.locator("#run-button").click()
        page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden", timeout=180000)
        with page.expect_download(timeout=45000) as event:
            page.locator("#result-download-link").click()
        output = OUT / f"docker-id161-notes-round{round_no}.pdf"
        event.value.save_as(output)
        with fitz.open(output) as compressed:
            text = [pdf_page.get_text() for pdf_page in compressed]
            assert text == source_text and len(compressed) == 69
            diffs = []
            for source_pix, output_page in zip(source_visuals, compressed):
                output_pix = output_page.get_pixmap(matrix=fitz.Matrix(.35, .35), alpha=False)
                a = Image.frombytes("RGB", (source_pix.width, source_pix.height), source_pix.samples)
                b = Image.frombytes("RGB", (output_pix.width, output_pix.height), output_pix.samples)
                diffs.append(sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3)
        result_meta = page.locator("#result-meta").inner_text()
        missed = "requested target could not be reached" in result_meta.lower()
        assert missed and marker in text[0] and not errors
        rounds.append({"round": round_no, "http_status": response.status,
                       "source_bytes": SOURCE.stat().st_size,
                       "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                       "output_bytes": output.stat().st_size, "output_pages": len(text),
                       "all_page_text_and_order_preserved": text == source_text,
                       "mean_rendered_rgb_difference_0_255": sum(diffs) / len(diffs),
                       "max_page_rendered_rgb_difference_0_255": max(diffs),
                       "target_100000_bytes_reached": output.stat().st_size < 100000,
                       "missed_target_warning_visible": missed, "result_meta": result_meta,
                       "download_name": event.value.suggested_filename, "page_errors": errors})
        context.close()
    browser.close()

import subprocess
image_id = subprocess.check_output(
    ["docker", "image", "inspect", "paperplane-v23-audit:codex-current", "--format", "{{.Id}}"], text=True
).strip()
evidence = {"image": "paperplane-v23-audit:codex-current", "image_id": image_id,
            "fixture": str(SOURCE), "source_pages": len(source_text), "source_marker": marker,
            "rounds": rounds}
(OUT / "browser-id161-docker-notes-compress.json").write_text(
    json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(evidence, indent=2, ensure_ascii=False))
