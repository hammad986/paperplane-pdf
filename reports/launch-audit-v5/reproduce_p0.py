from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8501"
PDF = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
OUT = ROOT / "reports" / "launch-audit-v5"
OUT.mkdir(parents=True, exist_ok=True)
evidence: dict[str, object] = {"page_errors": [], "console_errors": [], "requests": []}

def wait_text(locator, expected: str, timeout: float = 60) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if locator.count() and locator.inner_text().strip() == expected:
            return True
        time.sleep(0.1)
    return locator.count() > 0 and locator.inner_text().strip() == expected

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=True, viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("pageerror", lambda e: evidence["page_errors"].append(str(e)))
    page.on("console", lambda m: evidence["console_errors"].append(m.text) if m.type == "error" else None)
    page.on("response", lambda r: evidence["requests"].append({"status": r.status, "url": r.url}) if "/api/studio/" in r.url else None)
    page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
    deadline = time.time() + 20
    while time.time() < deadline:
        active = page.locator(".sidebar-tool-item.active")
        if active.count() and "merge" in active.inner_text().lower():
            break
        time.sleep(0.1)
    page.locator("#mob-nav-studio").click()
    page.locator("#studio-file-input").set_input_files(str(PDF))
    if not wait_text(page.locator("#studio-page-count"), "69", 90):
        raise RuntimeError("Studio failed to load the 69-page fixture")
    page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=45000)
    page.screenshot(path=str(OUT / "repro-studio-page1-375-before.png"), full_page=True)
    evidence["page1_open"] = {
        "canvas_rendered": page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").count() == 1,
        "current_page": page.locator("#page-jump-input").input_value(),
    }
    jump_results = []
    for target in [69, 1, 35]:
        page.locator("#page-jump-input").fill(str(target))
        page.locator("#page-jump-input").press("Enter")
        start = time.perf_counter()
        slot = page.locator(f"#studio-page-stack .studio-page-sheet.is-current[data-page='{target}']")
        canvas = slot.locator("canvas.pdf-page-canvas")
        rendered_immediately = canvas.get_attribute("data-rendered") == "true"
        try:
            canvas.wait_for(state="attached", timeout=1000)
            while time.perf_counter() - start < 30 and canvas.get_attribute("data-rendered") != "true":
                time.sleep(0.1)
            rendered_within_30s = canvas.get_attribute("data-rendered") == "true"
        except Exception:
            rendered_within_30s = False
        jump_results.append({"target": target, "input": page.locator("#page-jump-input").input_value(), "immediate": rendered_immediately, "rendered_within_30s": rendered_within_30s, "seconds": round(time.perf_counter() - start, 3)})
        page.screenshot(path=str(OUT / f"repro-studio-page{target}-375-before.png"), full_page=True)
    evidence["page_jumps"] = jump_results

    # Exercise Extract from an actual toolbar click with two selected pages.
    page.locator("#btn-mode-organize").click()
    page.locator("#organizer-grid .organizer-thumb-card[data-page='1'] .thumb-checkbox").check()
    page.locator("#organizer-grid .organizer-thumb-card[data-page='2'] .thumb-checkbox").check()
    extraction = {"selected": [1, 2], "download": False}
    started = time.perf_counter()
    try:
        with page.expect_download(timeout=45000) as dl_event:
            page.locator("#batch-extract-btn").click()
        dl = dl_event.value
        out_path = OUT / f"repro_{dl.suggested_filename}"
        dl.save_as(str(out_path))
        doc = fitz.open(out_path)
        extraction.update({"download": True, "filename": dl.suggested_filename, "bytes": out_path.stat().st_size, "page_count": doc.page_count, "text_chars": sum(len(pg.get_text()) for pg in doc), "seconds": round(time.perf_counter() - started, 3)})
        doc.close()
    except PlaywrightTimeout as exc:
        extraction.update({"timeout": str(exc).splitlines()[0], "toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None, "seconds": round(time.perf_counter() - started, 3)})
    page.screenshot(path=str(OUT / "repro-studio-extract-375-before.png"), full_page=True)
    evidence["extract"] = extraction

    # Reload retention sequence: open from route, go to page 5, delete page 69, reload.
    page.goto(f"{BASE}/merge-pdf", wait_until="domcontentloaded")
    deadline = time.time() + 20
    while time.time() < deadline:
        active = page.locator(".sidebar-tool-item.active")
        if active.count() and "merge" in active.inner_text().lower():
            break
        time.sleep(0.1)
    page.locator("#mob-nav-studio").click()
    page.locator("#studio-file-input").set_input_files(str(PDF))
    if not wait_text(page.locator("#studio-page-count"), "69", 90):
        raise RuntimeError("Studio failed second 69-page fixture load")
    page.locator("#page-jump-input").fill("5")
    page.locator("#page-jump-input").press("Enter")
    page.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='5'] canvas[data-rendered=true]").wait_for(timeout=45000)
    page.locator("#btn-mode-organize").click()
    page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox").check()
    page.locator("#batch-delete-btn").click()
    page.locator("dialog.app-confirm-dialog[open] .app-confirm-accept").click()
    wait_text(page.locator("#studio-page-count"), "68", 60)
    mutation_toast = page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None
    page.screenshot(path=str(OUT / "repro-studio-deleted-before-reload-375.png"), full_page=True)
    page.reload(wait_until="domcontentloaded")
    deadline = time.time() + 90
    while time.time() < deadline and page.locator("#studio-page-count").inner_text().strip() == "0":
        time.sleep(0.1)
    evidence["reload_retention"] = {
        "after_reload_url": page.url,
        "studio_active": page.locator("#app-shell.studio-active").count() == 1,
        "page_count_after_reload": page.locator("#studio-page-count").inner_text().strip(),
        "page_input_after_reload": page.locator("#page-jump-input").input_value(),
        "restored_toast": page.locator(".toast-notice").inner_text() if page.locator(".toast-notice").count() else None,
        "pre_reload_delete_toast": mutation_toast,
    }
    page.screenshot(path=str(OUT / "repro-studio-after-reload-375.png"), full_page=True)
    browser.close()

(OUT / "p0-reproduction.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(evidence, indent=2, ensure_ascii=False))
