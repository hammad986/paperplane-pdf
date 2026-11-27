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
BASE = "http://127.0.0.1:18502"
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
        organizer = page.evaluate("""appVersion=>({
          script:[...document.scripts].some(s=>s.src.endsWith('/assets/page_organizer.js?v=16')),
          appScript:[...document.scripts].some(s=>s.src.endsWith(`/assets/app.js?v=${appVersion}`)),
          observerMargin:window.PaperplanePageOrganizer?.observer?.rootMargin || null,
          mobilePageObserverMargin:window.state?.studio?.pageObserver?.rootMargin || null,
          count:document.querySelectorAll('#organizer-grid .organizer-thumb-card').length
        })""", APP_VERSION)
        assert organizer == {"script": True, "appScript": True, "observerMargin": "0px 0px 0px 0px",
                             "mobilePageObserverMargin": "0px 0px 0px 0px", "count": 69}, organizer
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
        output = ROOT / "reports" / "launch-audit-v23" / f"docker-id122-round{round_no}.pdf"
        event.value.save_as(output)
        with fitz.open(output) as result:
            actual = [pdf_page.get_text() for pdf_page in result]
            assert actual == expected and len(result) == 69
        width = page.evaluate("document.documentElement.scrollWidth")
        assert width == 390 and not errors, {"width": width, "errors": errors}
        rounds.append({"round": round_no, "http_status": response.status, "elapsed_seconds": round(perf_counter()-started, 2),
                       "output_bytes": output.stat().st_size, "pages": len(actual),
                       "all_page_text_and_order_preserved": True, "document_width": width,
                       "organizer_cards": organizer["count"], "page_one_thumbnail": True, "page_forty_thumbnail": True,
                       "organizer_script_cached_version": "v16", "intersection_observer_root_margin": organizer["observerMargin"],
                       "mobile_page_observer_root_margin": organizer["mobilePageObserverMargin"],
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
(OUT / f"browser-id122-docker-codex-final-v{APP_VERSION}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
