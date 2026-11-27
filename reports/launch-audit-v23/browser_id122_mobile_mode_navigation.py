"""Check that mobile Studio keeps page navigation working after mode changes."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import socket
import sys
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
if not SOURCE.is_file():
    raise FileNotFoundError(SOURCE)
with fitz.open(SOURCE) as source_document:
    EXPECTED_PAGE_TEXT = [page.get_text() for page in source_document]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

results = []
with TemporaryDirectory(prefix="paperplane-id122-mode-navigation-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(120):
            if app.poll() is not None:
                raise RuntimeError(f"Local app exited: {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("Local app did not start")

        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3,
                                              is_mobile=True, has_touch=True, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#studio-file-input").set_input_files(str(SOURCE))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
                page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
                page.wait_for_timeout(250)
                initial = page.evaluate("""() => ({mode:document.querySelector('#btn-mode-organize')?.classList.contains('active')?'organize':'annotate',
                  drawer:document.querySelector('#app-shell')?.classList.contains('studio-pages-open'),
                  page:state.studio.currentPage})""")
                page.evaluate("""() => {
                  const native=HTMLElement.prototype.getBoundingClientRect;
                  window.__geometryReads=0;
                  HTMLElement.prototype.getBoundingClientRect=function(...args){
                    if(new Error().stack?.includes('syncStudioMobilePagesPanelPosition')) window.__geometryReads++;
                    return native.apply(this,args);
                  };
                }""")
                page.evaluate("document.querySelector('#btn-mode-annotate').click()")
                page.wait_for_timeout(50)
                annotate_reads = page.evaluate("window.__geometryReads")
                page.evaluate("""() => {window.__geometryReads=0;document.querySelector('#btn-mode-organize').click();}""")
                page.wait_for_timeout(50)
                organize_reads = page.evaluate("window.__geometryReads")
                if initial["mode"] == "annotate":
                    page.evaluate("document.querySelector('#btn-mode-annotate').click()")
                current_drawer = page.evaluate("document.querySelector('#app-shell')?.classList.contains('studio-pages-open')")
                if current_drawer != initial["drawer"]:
                    page.evaluate("document.querySelector('#studio-mobile-pages-btn').click()")
                page.wait_for_timeout(200)

                page.locator('.studio-page-sheet[data-page="40"]').scroll_into_view_if_needed(timeout=15000)
                try:
                    page.wait_for_function("state.studio.currentPage >= 39 && state.studio.currentPage <= 41", timeout=30000)
                    page40 = True
                    diagnostic = page.evaluate("""() => ({current:state.studio.currentPage,scrollTop:document.querySelector('#studio-canvas-area')?.scrollTop,
                      mode:document.querySelector('#btn-mode-organize')?.classList.contains('active')?'organize':'annotate',
                      drawer:document.querySelector('#app-shell')?.classList.contains('studio-pages-open'),
                      target:document.querySelector('.studio-page-sheet[data-page=\"40\"]')?.getBoundingClientRect().toJSON()})""")
                except Exception:
                    page40 = False
                    diagnostic = page.evaluate("""() => ({current:state.studio.currentPage,scrollTop:document.querySelector('#studio-canvas-area')?.scrollTop,
                      documentScroll:document.scrollingElement?.scrollTop,
                      mode:document.querySelector('#btn-mode-organize')?.classList.contains('active')?'organize':'annotate',
                      drawer:document.querySelector('#app-shell')?.classList.contains('studio-pages-open'),
                      target:document.querySelector('.studio-page-sheet[data-page=\"40\"]')?.getBoundingClientRect().toJSON(),
                      observer:!!state.studio.pageObserver})""")
                results.append({"round":round_no,"initial":initial,"annotate_geometry_reads":annotate_reads,
                                "organize_geometry_reads":organize_reads,"page40_navigation":page40,
                                "diagnostic":diagnostic,"page_errors":errors.copy()})
                if not page40:
                    raise AssertionError(f"Page 40 navigation failed after mode changes: {diagnostic}")
                assert annotate_reads == organize_reads == 1, results[-1]
                page.locator('.studio-page-sheet[data-page="1"]').scroll_into_view_if_needed(timeout=15000)
                page.wait_for_function("state.studio.currentPage === 1", timeout=30000)
                with page.expect_download(timeout=120000) as download_event:
                    page.locator("#save-studio-btn").click()
                output_pdf = Path(temporary) / f"mode-navigation-round-{round_no}.pdf"
                download_event.value.save_as(output_pdf)
                with fitz.open(output_pdf) as result_document:
                    actual_page_text = [pdf_page.get_text() for pdf_page in result_document]
                assert actual_page_text == EXPECTED_PAGE_TEXT, {
                    "round": round_no, "pages": len(actual_page_text),
                    "first_page_matches": bool(actual_page_text and actual_page_text[0] == EXPECTED_PAGE_TEXT[0]),
                    "last_page_matches": bool(actual_page_text and actual_page_text[-1] == EXPECTED_PAGE_TEXT[-1]),
                }
                results[-1]["download"] = {"pages": len(actual_page_text), "text_and_order_preserved": True,
                                            "bytes": output_pdf.stat().st_size}
                context.close()
            browser.close()
        assert not errors, errors
        report = {"rounds":results,"page_errors":errors,"verdict":"PASS"}
        output = OUT / "browser-id122-mobile-mode-navigation.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=8)
