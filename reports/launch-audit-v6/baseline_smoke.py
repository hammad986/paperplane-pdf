from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8501"
NOTES = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
SAMPLE = ROOT / "reports" / "launch-audit-v5" / "catalog-samples" / "audit-sample.pdf"


def wait_text(page, selector: str, expected: str, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.locator(selector).count() and page.locator(selector).inner_text().strip() == expected:
            return True
        time.sleep(0.1)
    return page.locator(selector).count() > 0 and page.locator(selector).inner_text().strip() == expected


def file_info(path: Path) -> dict[str, object]:
    doc = fitz.open(path)
    try:
        return {"path": str(path), "pages": doc.page_count, "bytes": path.stat().st_size, "first_page_text": doc[0].get_text()[:300]}
    finally:
        doc.close()


evidence: dict[str, object] = {"base": BASE, "fixture": file_info(NOTES), "merge_input": file_info(SAMPLE), "page_errors": [], "console_errors": []}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # Capture the current AI Docs empty and loaded states before changing code.
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True, accept_downloads=True)
    page = context.new_page()
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
    page.evaluate("window.switchWorkspaceView('ai', null, false)")
    page.locator("#view-ai-studio").wait_for(state="visible")
    page.screenshot(path=str(OUT / "before-ai-empty-375.png"), full_page=True)
    page.locator("#ai-file-input").set_input_files(str(NOTES))
    page.locator("#ai-active-doc-bar").wait_for(state="visible", timeout=60000)
    page.screenshot(path=str(OUT / "before-ai-loaded-375.png"), full_page=True)
    button = page.locator("#trigger-summary-btn")
    summary = {"button_disabled": button.is_disabled(), "initial_text": page.locator("#summary-display").inner_text().strip()}
    started = time.monotonic()
    try:
        response = page.request.post(f"{BASE}/api/ai/summarize", multipart={"file": {"name": NOTES.name, "mimeType": "application/pdf", "buffer": NOTES.read_bytes()}})
        summary.update({"http_status": response.status, "elapsed_seconds": round(time.monotonic() - started, 3), "body": response.text()[:1000]})
    except Exception as exc:
        summary.update({"error": str(exc), "elapsed_seconds": round(time.monotonic() - started, 3)})
    evidence["ai_summary_baseline"] = summary
    context.close()

    # Run a real Merge PDF workflow through the user-facing tool UI.
    context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    page = context.new_page()
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not page.locator("#file-input").evaluate("element => element.multiple"):
        time.sleep(0.1)
    page.locator("#file-input").set_input_files([str(NOTES), str(SAMPLE)])
    page.locator("#run-button").wait_for(state="visible", timeout=30000)
    deadline = time.monotonic() + 30
    while page.locator("#run-button").is_disabled() and time.monotonic() < deadline:
        time.sleep(0.1)
    started = time.monotonic()
    page.locator("#run-button").click()
    page.locator("#result").wait_for(state="visible", timeout=120000)
    merge = {"elapsed_seconds": round(time.monotonic() - started, 3), "result_meta": page.locator("#result-meta").inner_text().strip()}
    with page.expect_download(timeout=45000) as download_event:
        page.locator("#result-download-link").click()
    download = download_event.value
    output = OUT / "before-merge-output.pdf"
    download.save_as(str(output))
    merge.update({"filename": download.suggested_filename, "download": file_info(output)})
    evidence["merge_baseline"] = merge
    page.screenshot(path=str(OUT / "before-merge-1366.png"), full_page=True)
    context.close()

    # Reproduce the reported 69-page deletion -> reload -> reload retention path.
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    page.locator("#studio-file-input").set_input_files(str(NOTES))
    if not wait_text(page, "#studio-page-count", "69", 90):
        raise RuntimeError(f"Baseline Studio fixture did not load: {page.locator('#studio-page-count').inner_text()!r}")
    page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=45000)
    page.locator("#page-jump-input").fill("5")
    page.locator("#page-jump-input").press("Enter")
    page.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='5'] canvas[data-rendered=true]").wait_for(timeout=45000)
    page.locator("#btn-mode-organize").click()
    page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox").check()
    page.locator("#batch-delete-btn").click()
    page.locator("dialog.app-confirm-dialog[open] .app-confirm-accept").click()
    wait_text(page, "#studio-page-count", "68", 60)
    before_reload = {"count": page.locator("#studio-page-count").inner_text().strip(), "toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None}
    page.screenshot(path=str(OUT / "before-studio-deleted-375.png"), full_page=True)
    reloads = []
    for number in (1, 2):
        page.reload(wait_until="domcontentloaded")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and (not page.locator("#studio-page-count").count() or page.locator("#studio-page-count").inner_text().strip() == "0"):
            time.sleep(0.1)
        reloads.append({
            "reload": number,
            "count": page.locator("#studio-page-count").inner_text().strip() if page.locator("#studio-page-count").count() else None,
            "page": page.locator("#page-jump-input").input_value() if page.locator("#page-jump-input").count() else None,
            "toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None,
        })
    evidence["studio_delete_baseline"] = {"before_reload": before_reload, "after_reloads": reloads}
    page.screenshot(path=str(OUT / "before-studio-after-reload-375.png"), full_page=True)
    context.close()
    browser.close()

(OUT / "baseline-smoke.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(evidence, indent=2, ensure_ascii=False))
