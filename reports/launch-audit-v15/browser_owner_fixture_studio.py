"""Delete/reload/download checks using the supplied 68-page edited PDF."""
from __future__ import annotations

import fitz
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\mdham\Downloads\edited_notes-69page.pdf")
HELPER_PATH = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("owner_studio_helpers", HELPER_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)


def texts(path: Path) -> list[str]:
    with fitz.open(path) as document:
        return [page.get_text().strip() for page in document]


def main() -> None:
    original = texts(SOURCE)
    if len(original) != 68:
        raise AssertionError(f"Expected supplied edited fixture to have 68 pages, got {len(original)}")
    results = []
    with tempfile.TemporaryDirectory(prefix="paperplane-owner-studio-") as temp:
        app, base, identities = helpers.start_server(Path(temp))
        try:
            port = int(urlsplit(base).port)
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local app exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local app did not become ready")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": identities["accounts"][0][1],
                                      "url": base, "httpOnly": True}])
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error).splitlines()[0][:180]))
                for number in (1, 2):
                    page.goto(base + "/studio", wait_until="domcontentloaded")
                    page.locator("#topbar-auth-user").wait_for(state="visible")
                    page.locator("#studio-file-input").set_input_files(str(SOURCE))
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'",
                                           timeout=30000)
                    card = page.locator('.organizer-thumb-card[data-page="68"]')
                    card.wait_for(state="visible", timeout=30000)
                    jump_timings = []
                    for target_page in (68, 1):
                        started = time.perf_counter()
                        jump = page.locator("#page-jump-input")
                        jump.fill(str(target_page))
                        jump.press("Enter")
                        page.locator(
                            f"#studio-page-stack .studio-page-sheet.is-current[data-page='{target_page}'] canvas[data-rendered='true']"
                        ).wait_for(timeout=30000)
                        jump_timings.append(round(time.perf_counter() - started, 2))
                    page.locator("#btn-mode-organize").click()
                    card = page.locator('.organizer-thumb-card[data-page="68"]')
                    card.scroll_into_view_if_needed()
                    mutation_started = time.perf_counter()
                    page.evaluate("() => { window.PaperplanePageOrganizer.deletePages([68]); }")
                    confirm = page.locator(".app-confirm-dialog .app-confirm-accept")
                    confirm.wait_for(state="visible", timeout=5000)
                    with page.expect_response("**/api/studio/page/delete", timeout=30000) as response:
                        confirm.click()
                    assert response.value.status == 200
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67'",
                                           timeout=30000)
                    delete_to_count_seconds = round(time.perf_counter() - mutation_started, 2)
                    undo_banner = page.locator("#studio-undo-banner")
                    undo_banner.wait_for(state="visible", timeout=5000)
                    assert undo_banner.get_by_role("button", name="Undo").is_enabled()
                    undo_banner.get_by_role("button", name="Undo").click()
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'",
                                           timeout=30000)
                    with page.expect_download(timeout=30000) as restored_event:
                        page.locator("#save-studio-btn").click()
                    restored_output = Path(temp) / f"owner-studio-undo-{number}.pdf"
                    restored_event.value.save_as(restored_output)
                    assert texts(restored_output) == original

                    # Repeat the deletion and reload to ensure the Undo check
                    # does not hide a stale-workspace persistence regression.
                    page.evaluate("() => { window.PaperplanePageOrganizer.deletePages([68]); }")
                    confirm = page.locator(".app-confirm-dialog .app-confirm-accept")
                    confirm.wait_for(state="visible", timeout=5000)
                    with page.expect_response("**/api/studio/page/delete", timeout=30000) as response:
                        confirm.click()
                    assert response.value.status == 200
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67'",
                                           timeout=30000)
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '67'",
                                           timeout=30000)
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#save-studio-btn").click()
                    output = Path(temp) / f"owner-studio-{number}.pdf"
                    event.value.save_as(output)
                    assert texts(output) == original[:67]
                    assert not errors, errors
                    results.append({"round": number, "input_pages": 68, "retained_pages": 67,
                                    "reload_retained_deletion": True, "download_content_matches": True,
                                    "delete_to_count_seconds": delete_to_count_seconds,
                                    "undo_banner_and_restore_verified": True,
                                    "page_68_then_1_render_seconds": jump_timings,
                                    "page_errors": errors})
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except Exception:
                app.kill()
                app.wait(timeout=5)
    report = Path(__file__).with_name("browser-owner-fixture-studio.json")
    report.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
