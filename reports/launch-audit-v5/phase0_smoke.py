from __future__ import annotations

import json
import sys
import time
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8501"
STUDIO_PDF = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
TOOL_PDF = ROOT / "runtime_data_codex_audit" / "color-audit.pdf"
OUT = ROOT / "reports" / "launch-audit-v5"
OUT.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")

evidence: dict[str, object] = {"base": BASE, "console_errors": [], "page_errors": [], "failed_requests": []}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=True, viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
    page.on("requestfailed", lambda req: evidence["failed_requests"].append({"url": req.url, "error": req.failure}))
    page.goto(f"{BASE}/download", wait_until="domcontentloaded")
    page.evaluate("window.switchWorkspaceView('studio', null, false)")
    page.locator("#studio-file-input").set_input_files(str(STUDIO_PDF))
    deadline = time.time() + 90
    while time.time() < deadline and page.locator("#studio-page-count").inner_text().strip() != "69":
        time.sleep(0.2)
    if page.locator("#studio-page-count").inner_text().strip() != "69":
        raise RuntimeError(f"Studio did not load 69 pages; count={page.locator('#studio-page-count').inner_text()!r}")
    page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=45000)
    page.screenshot(path=str(OUT / "phase0-studio-375.png"), full_page=True)
    evidence["studio"] = {
        "url": page.url,
        "page_count": page.locator("#studio-page-count").inner_text(),
        "current_page": page.locator("#page-jump-input").input_value(),
        "rendered_canvas_count": page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").count(),
        "screenshot": str(OUT / "phase0-studio-375.png"),
    }

    tool = context.new_page()
    tool.set_viewport_size({"width": 1280, "height": 900})
    tool.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
    tool.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
    tool.on("requestfailed", lambda req: evidence["failed_requests"].append({"url": req.url, "error": req.failure}))
    tool.goto(f"{BASE}/convert-pdf-to-grayscale", wait_until="domcontentloaded")
    deadline = time.time() + 20
    while time.time() < deadline:
        active_tool = tool.locator(".sidebar-tool-item.active")
        if active_tool.count() and "grayscale" in active_tool.inner_text().lower():
            break
        time.sleep(0.1)
    active_tool = tool.locator(".sidebar-tool-item.active")
    if not active_tool.count() or "grayscale" not in active_tool.inner_text().lower():
        raise RuntimeError(f"Tool route did not initialize the grayscale workflow; title={tool.locator('#tool-title').inner_text()!r}, active={active_tool.inner_text() if active_tool.count() else None!r}")
    tool.locator("#file-input").set_input_files(str(TOOL_PDF))
    deadline = time.time() + 10
    while time.time() < deadline and "grayscale" not in tool.locator("#run-button").inner_text().lower():
        time.sleep(0.1)
    run_label = tool.locator("#run-button").inner_text().strip()
    if "grayscale" not in run_label.lower():
        raise RuntimeError(f"Grayscale run button not initialized after file selection: {run_label!r}")
    tool.locator("#run-button").click()
    tool.locator("#result").wait_for(state="visible", timeout=90000)
    result_meta = tool.locator("#result-meta").inner_text()
    with tool.expect_download(timeout=30000) as download_event:
        tool.locator("#result-download-link").click()
    download = download_event.value
    target = OUT / f"phase0_{download.suggested_filename}"
    download.save_as(str(target))

    doc = fitz.open(target)
    pix = doc[0].get_pixmap(alpha=False)
    samples = pix.samples
    rgb = [samples[i : i + 3] for i in range(0, len(samples), 3)]
    colored_pixels = sum(1 for r, g, b in rgb if max(r, g, b) - min(r, g, b) > 5)
    evidence["tool_smoke"] = {
        "route": tool.url,
        "tool_title": tool.locator("#tool-title").inner_text(),
        "run_button": run_label,
        "operation": "Convert to Grayscale",
        "result_banner": result_meta,
        "download_filename": download.suggested_filename,
        "download_bytes": target.stat().st_size,
        "output_page_count": doc.page_count,
        "output_text": doc[0].get_text()[:500],
        "output_color_pixel_count": colored_pixels,
        "output_pixels_checked": len(rgb),
        "output_pdf_opened": True,
        "saved_output": str(target),
    }
    doc.close()
    browser.close()

(OUT / "phase0-smoke.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(evidence, indent=2, ensure_ascii=False))
