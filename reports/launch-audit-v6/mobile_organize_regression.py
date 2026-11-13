from __future__ import annotations

import json
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PDF = ROOT / "runtime_data_codex_audit" / "notes_69pages_audit.pdf"
BASE = "http://127.0.0.1:8501"


def wait_for_count(page, expected: int, timeout: float = 30) -> float:
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        if page.locator("#studio-page-count").count() and page.locator("#studio-page-count").inner_text().strip() == str(expected):
            return round(time.monotonic() - started, 3)
        time.sleep(0.1)
    raise AssertionError(f"Expected {expected} pages, saw {page.locator('#studio-page-count').inner_text()!r}")


def export_pdf(page, filename: str) -> fitz.Document:
    with page.expect_download(timeout=45_000) as download_event:
        page.locator("#save-studio-btn").click()
    path = OUT / filename
    download_event.value.save_as(str(path))
    return fitz.open(path)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
    page.locator("#studio-file-input").set_input_files(str(PDF))
    wait_for_count(page, 69, 90)
    page.locator("#studio-page-stack .studio-page-sheet.is-current canvas[data-rendered=true]").wait_for(timeout=45_000)
    page.locator("#page-jump-input").fill("35")
    page.locator("#page-jump-input").press("Enter")
    page.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='35'] canvas[data-rendered=true]").wait_for(timeout=30_000)

    page.locator("#btn-mode-organize").click()
    page.locator("#studio-thumbnails-bar").wait_for(state="visible")
    assert page.locator("#studio-mobile-pages-btn").get_attribute("aria-expanded") == "true"
    page.screenshot(path=str(OUT / "mobile-organize-drawer-375.png"))

    page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox-label").click()
    checkbox = page.locator("#organizer-grid .organizer-thumb-card[data-page='69'] .thumb-checkbox")
    assert checkbox.is_checked()
    batch = page.locator("#organizer-batch-bar")
    assert batch.is_visible()
    assert batch.evaluate("el => el.parentElement.id") == "studio-mobile-batch-slot"
    delete_button = page.locator("#batch-delete-btn")
    assert delete_button.is_visible() and delete_button.is_enabled()
    page.screenshot(path=str(OUT / "mobile-organize-selected-375.png"))

    delete_button.click()
    confirm = page.locator("dialog.app-confirm-dialog[open]")
    confirm.wait_for(state="visible")
    confirm_text = confirm.inner_text()
    assert "undo this for 10 seconds" in confirm_text
    confirm.locator(".app-confirm-accept").click()
    deletion_seconds = wait_for_count(page, 68, 45)
    after_delete_position = page.locator("#page-jump-input").input_value()
    assert after_delete_position == "35", after_delete_position

    reloads = []
    for number in (1, 2):
        page.reload(wait_until="domcontentloaded")
        elapsed = wait_for_count(page, 68, 90)
        restored_position = page.locator("#page-jump-input").input_value()
        assert restored_position == "35", {"reload": number, "page": restored_position}
        reloads.append({"reload": number, "pageCount": 68, "page": restored_position, "restoreSeconds": elapsed})
    page.screenshot(path=str(OUT / "mobile-organize-delete-retained-375.png"))

    # Reorder a page using the visible mobile batch controls, then verify the
    # actual exported page text after two reloads.
    page.locator("#btn-mode-organize").click()
    page.locator("#organizer-grid .organizer-thumb-card[data-page='35'] .thumb-checkbox-label").click()
    page.locator("#batch-move-down-btn").click()
    page.locator(".toast-notice", has_text="Pages reordered successfully.").wait_for(state="visible", timeout=45_000)
    page.locator("#page-jump-input").wait_for(state="visible")
    reorder_reload = []
    for number in (1, 2):
        page.reload(wait_until="domcontentloaded")
        elapsed = wait_for_count(page, 68, 90)
        reorder_reload.append({"reload": number, "pageCount": 68, "restoreSeconds": elapsed})
    reordered = export_pdf(page, "after-studio-reordered.pdf")
    before_reorder_text = (reordered[34].get_text(), reordered[35].get_text())
    assert "Page 36" in before_reorder_text[0] and "Page 35" in before_reorder_text[1], before_reorder_text
    reordered.close()

    # Duplicate the active page from the visible toolbar and verify that the
    # duplicate survives reload with the same actual text in adjacent pages.
    page.locator("#page-jump-input").fill("35")
    page.locator("#page-jump-input").press("Enter")
    page.locator("#studio-page-stack .studio-page-sheet.is-current[data-page='35'] canvas[data-rendered=true]").wait_for(timeout=30_000)
    page.locator("#btn-mode-annotate").click()
    page.locator("#editor-dup-page-btn").click()
    wait_for_count(page, 69, 45)
    duplicate_reload = []
    for number in (1, 2):
        page.reload(wait_until="domcontentloaded")
        elapsed = wait_for_count(page, 69, 90)
        duplicate_reload.append({"reload": number, "pageCount": 69, "page": page.locator("#page-jump-input").input_value(), "restoreSeconds": elapsed})
    duplicated = export_pdf(page, "after-studio-duplicated.pdf")
    duplicate_text = (duplicated[34].get_text(), duplicated[35].get_text())
    assert duplicate_text[0] == duplicate_text[1], (duplicate_text[0][:160], duplicate_text[1][:160])
    duplicated.close()

    result = {
        "viewport": {"width": 375, "height": 812},
        "beforePages": 69,
        "organizeDrawerOpens": True,
        "selectedPage": 69,
        "selectionActionsInDrawer": True,
        "deleteConfirmation": confirm_text,
        "deleteSeconds": deletion_seconds,
        "afterPages": 68,
        "positionAfterDelete": after_delete_position,
        "reloads": reloads,
        "reorderReloads": reorder_reload,
        "reorderedPages35And36": ["Page 36", "Page 35"],
        "duplicateReloads": duplicate_reload,
        "duplicateAdjacentPagesMatch": True,
        "pageErrors": errors,
        "screenshots": [
            "mobile-organize-drawer-375.png",
            "mobile-organize-selected-375.png",
            "mobile-organize-delete-retained-375.png",
        ],
    }
    assert not errors, errors
    print(json.dumps(result, indent=2))
    context.close()
    browser.close()
