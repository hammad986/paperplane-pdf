"""Content-check the 69-page Studio export in the latest production Docker image."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from time import perf_counter

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
BASE = "http://127.0.0.1:18507"
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
IMAGE_TAG = os.environ.get("PAPERPLANE_TEST_IMAGE_TAG", "paperplane-v23-audit:codex-current")
APP_VERSION = re.search(r'/assets/app\.js\?v=(\d+)', (ROOT / "web" / "index.html").read_text(encoding="utf-8")).group(1)
with fitz.open(SOURCE) as source:
    expected = [page.get_text() for page in source]
assert len(expected) == 69
rounds = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    for round_no in (1, 2):
        context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True,
                                      has_touch=True, accept_downloads=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        cdp = context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        started = perf_counter()
        response = page.goto(f"{BASE}/studio", wait_until="domcontentloaded", timeout=30000)
        assert response and response.status == 200
        page.locator("#studio-file-input").set_input_files(str(SOURCE))
        page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
        page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
        mobile_pages = page.locator("#studio-mobile-pages-btn")
        if mobile_pages.is_visible() and mobile_pages.get_attribute("aria-expanded") != "true":
            mobile_pages.click()
        page.wait_for_function("document.querySelectorAll('#organizer-grid .organizer-thumb-card').length === 69", timeout=30000)
        page.wait_for_function("document.querySelector('.organizer-thumb-card[data-page=\"1\"] .thumb-rendered-img')", timeout=30000)
        organizer = page.evaluate("""()=>({
          script:[...document.scripts].some(s=>s.src.endsWith('/assets/page_organizer.js?v=19')),
          observerMargin:window.PaperplanePageOrganizer?.observer?.rootMargin || null,
          count:document.querySelectorAll('#organizer-grid .organizer-thumb-card').length
        })""")
        assert organizer == {"script": True, "observerMargin": "0px 0px 0px 0px", "count": 69}, organizer
        page.evaluate("""() => {
          const native = HTMLElement.prototype.getBoundingClientRect;
          window.__toolbarInitialState = {
            mode: document.querySelector('#btn-mode-organize')?.classList.contains('active') ? 'organize' : 'annotate',
            pagesOpen: document.querySelector('#app-shell')?.classList.contains('studio-pages-open')
          };
          window.__toolbarGeometryReads = 0;
          HTMLElement.prototype.getBoundingClientRect = function(...args) {
            if (new Error().stack?.includes('syncStudioMobilePagesPanelPosition')) window.__toolbarGeometryReads++;
            return native.apply(this, args);
          };
        }""")
        page.evaluate("document.querySelector('#btn-mode-annotate').click()")
        page.wait_for_timeout(50)
        annotate_geometry_reads = page.evaluate("window.__toolbarGeometryReads")
        page.evaluate("""() => {window.__toolbarGeometryReads=0; document.querySelector('#btn-mode-organize').click();}""")
        page.wait_for_timeout(50)
        organize_geometry_reads = page.evaluate("window.__toolbarGeometryReads")
        assert annotate_geometry_reads == organize_geometry_reads == 0, {
            "annotate": annotate_geometry_reads, "organize": organize_geometry_reads,
        }
        page.evaluate("window.__toolbarGeometryReads=0")
        page.locator("#org-select-all-btn").click()
        select_all_geometry_reads = page.evaluate("window.__toolbarGeometryReads")
        assert select_all_geometry_reads == 0, {"select_all": select_all_geometry_reads}
        page.evaluate("window.__toolbarGeometryReads=0")
        for page_num in (1, 2, 3):
            page.locator(f'.organizer-thumb-card[data-page="{page_num}"] .thumb-checkbox-label').click()
        repeated_selection_geometry_reads = page.evaluate("window.__toolbarGeometryReads")
        assert repeated_selection_geometry_reads == 0, {
            "repeated_selection": repeated_selection_geometry_reads,
        }
        page.evaluate("window.__toolbarGeometryReads=0")
        page.locator("#batch-clear-btn").click()
        clear_selection_geometry_reads = page.evaluate("window.__toolbarGeometryReads")
        assert clear_selection_geometry_reads == 0, {"clear_selection": clear_selection_geometry_reads}
        pages_top = page.evaluate("""() => ({
          variable: getComputedStyle(document.querySelector('#studio-thumbnails-bar')).getPropertyValue('--studio-mobile-pages-top').trim(),
          expected: `${Math.max(68, Math.ceil(document.querySelector('#studio-toolbar').getBoundingClientRect().bottom + 8))}px`
        })""")
        assert pages_top["variable"] == pages_top["expected"], pages_top
        initial_toolbar_state = page.evaluate("window.__toolbarInitialState")
        if initial_toolbar_state["mode"] == "annotate":
            page.evaluate("document.querySelector('#btn-mode-annotate').click()")
        current_drawer_open = page.evaluate("document.querySelector('#app-shell')?.classList.contains('studio-pages-open')")
        if current_drawer_open != initial_toolbar_state["pagesOpen"]:
            page.evaluate("document.querySelector('#studio-mobile-pages-btn').click()")
        page.wait_for_timeout(50)
        canvas = page.evaluate("""()=>{
          const element=document.querySelector('.studio-page-sheet[data-page="1"] .pdf-page-canvas');
          const pixels=element.getContext('2d').getImageData(0,0,element.width,element.height).data;
          let nonwhite=0;
          for(let i=0;i<pixels.length;i+=4) if(pixels[i]<235||pixels[i+1]<235||pixels[i+2]<235) nonwhite++;
          return {devicePixelRatio, width:element.width, cssWidth:parseInt(element.style.width,10),
            height:element.height, cssHeight:parseInt(element.style.height,10), nonwhitePixels:nonwhite};
        }""")
        canvas_scale = canvas["width"] / canvas["cssWidth"]
        assert canvas["devicePixelRatio"] == 3 and 1 <= canvas_scale <= 1.51, canvas
        assert canvas["nonwhitePixels"] > 100, canvas
        page.locator('.studio-page-sheet[data-page="40"]').scroll_into_view_if_needed()
        page.wait_for_function("state.studio.currentPage >= 39 && state.studio.currentPage <= 41", timeout=30000)
        page.wait_for_function("document.querySelector('.organizer-thumb-card[data-page=\"40\"] .thumb-rendered-img')", timeout=30000)
        page.locator('.studio-page-sheet[data-page="1"]').scroll_into_view_if_needed()
        page.wait_for_function("state.studio.currentPage === 1", timeout=30000)
        with page.expect_download(timeout=120000) as event:
            page.locator("#save-studio-btn").click()
        output = ROOT / "reports" / "launch-audit-v23" / f"docker-id122-v142-round{round_no}.pdf"
        event.value.save_as(output)
        with fitz.open(output) as result:
            actual = [pdf_page.get_text() for pdf_page in result]
            assert actual == expected and len(result) == 69
        width = page.evaluate("document.documentElement.scrollWidth")
        assert width == 390 and not errors, {"width": width, "errors": errors}
        rounds.append({"round": round_no, "http_status": response.status, "elapsed_seconds": round(perf_counter()-started, 2),
                       "output_bytes": output.stat().st_size, "pages": len(actual),
                       "all_page_text_and_order_preserved": True, "document_width": width,
                       "mobile_mode_geometry_reads": {"annotate": annotate_geometry_reads,
                                                       "organize": organize_geometry_reads},
                       "selection_toolbar_geometry_reads": {
                           "select_all": select_all_geometry_reads,
                           "unchanged_visible_selection_updates": repeated_selection_geometry_reads,
                           "clear": clear_selection_geometry_reads,
                       },
                        "pages_panel_top": pages_top["variable"],
                       "organizer_cards": organizer["count"], "page_one_thumbnail": True, "page_forty_thumbnail": True,
                       "organizer_script_cached_version": "v19", "intersection_observer_root_margin": organizer["observerMargin"],
                       "device_pixel_ratio": canvas["devicePixelRatio"], "canvas_scale": round(canvas_scale, 3),
                       "canvas": canvas, "page_errors": errors})
        context.close()
    browser.close()

image_id = subprocess.check_output(
    ["docker", "image", "inspect", IMAGE_TAG, "--format", "{{.Id}}"],
    text=True,
).strip()
report = {"image": IMAGE_TAG, "image_id": image_id,
          "fixture": str(SOURCE), "fixture_pages": len(expected), "cpu_throttle_rate": 4,
          "rounds": rounds}
(OUT / f"browser-id122-docker-codex-final-v{APP_VERSION}-v142.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

