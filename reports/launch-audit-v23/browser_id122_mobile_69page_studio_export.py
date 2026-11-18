"""Low-end mobile-emulation test for opening and exporting a real 69-page PDF in Studio."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
EXERCISE_SLOT_FALLBACK = os.environ.get("PAPERPLANE_TEST_SLOT_FALLBACK", "1") != "0"
if not SOURCE.is_file():
    raise FileNotFoundError(SOURCE)
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with fitz.open(SOURCE) as source_doc:
    expected_pages = len(source_doc)
    expected_text = [page.get_text() for page in source_doc]
assert expected_pages == 69, f"Expected the recorded 69-page fixture, got {expected_pages}"

rounds = []
with TemporaryDirectory(prefix="paperplane-id122-mobile-studio-") as temporary:
    temp = Path(temporary)
    app, base, _ = helper.start_server(temp / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                              has_touch=True, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                cdp = context.new_cdp_session(page)
                throttle_rate = float(os.environ.get("PAPERPLANE_CPU_THROTTLE", "4"))
                cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle_rate})
                page.add_init_script("""window.__longTasks=[];new PerformanceObserver(list=>
                  window.__longTasks.push(...list.getEntries().map(e=>({duration:e.duration,start:e.startTime,
                    attribution:[...(e.attribution||[])].map(a=>({containerType:a.containerType,containerName:a.containerName,containerSrc:a.containerSrc}))})))
                ).observe({type:'longtask',buffered:true});""")

                started = time.perf_counter()
                response = page.goto(f"{base}/studio", wait_until="domcontentloaded", timeout=30000)
                assert response and response.status == 200
                page.evaluate("""()=>{
                  window.__studioPhases=[];
                  const organizer=window.PaperplanePageOrganizer;
                  if(organizer){
                    const original=organizer.renderThumbnails.bind(organizer);
                    organizer.renderThumbnails=async(...args)=>{
                      const started=performance.now();
                      const result=await original(...args);
                      window.__studioPhases.push({phase:'organizer-thumbnails',duration:performance.now()-started});
                      return result;
                    };
                    const renderCard=organizer._renderCardCanvas.bind(organizer);
                    organizer._renderCardCanvas=async(card,pageNum)=>{
                      const started=performance.now();
                      const result=await renderCard(card,pageNum);
                      window.__studioPhases.push({phase:'thumbnail-page',page:pageNum,duration:performance.now()-started});
                      return result;
                    };
                  }
                }""")
                page.locator("#studio-file-input").set_input_files(str(SOURCE))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
                page.wait_for_function("document.querySelectorAll('#organizer-grid .organizer-thumb-card').length === 69", timeout=30000)
                page.locator("#org-select-all-btn").evaluate("button => button.click()")
                page.wait_for_function("window.PaperplanePageOrganizer.state.selectedPages.size === 69")
                all_cards_selected = page.locator("#organizer-grid .organizer-thumb-card.selected").count() == 69
                assert all_cards_selected
                page.locator("#org-invert-btn").evaluate("button => button.click()")
                page.wait_for_function("window.PaperplanePageOrganizer.state.selectedPages.size === 0")
                try:
                    page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=60000)
                except Exception:
                    diagnostics = page.evaluate("""()=>({overlay:document.querySelector('#studio-loading-text')?.textContent,
                      overlayHidden:document.querySelector('#studio-loading-overlay')?.hidden,
                      pageOne:document.querySelector('.studio-page-sheet[data-page=\"1\"]')?.outerHTML.slice(0,1000),
                      pageCount:document.querySelector('#page-total-indicator')?.textContent,
                      errors:window.__longTasks||[]})""")
                    raise AssertionError(f"Studio first page did not render: {diagnostics}")
                first_page_ready = time.perf_counter()
                fallback_recreated = None
                if EXERCISE_SLOT_FALLBACK:
                    # Exercise the live-stack fallback used if a page slot was
                    # pruned/replaced: it must append into the real stack and render.
                    page.evaluate("document.querySelector('.studio-page-sheet[data-page=\"2\"]')?.remove()")
                    page.evaluate("window.jumpToStudioPage(2)")
                    page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"2\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
                    fallback_recreated = page.locator('.studio-page-sheet[data-page="2"]').count() == 1
                page.locator("#save-studio-btn").scroll_into_view_if_needed()
                assert page.locator("#save-studio-btn").is_visible()
                export_started = time.perf_counter()
                with page.expect_download(timeout=120000) as event:
                    page.locator("#save-studio-btn").click()
                output_path = temp / f"id122-round{round_no}-{event.value.suggested_filename}"
                event.value.save_as(output_path)
                with fitz.open(output_path) as result:
                    actual_text = [page.get_text() for page in result]
                    assert len(result) == expected_pages, (len(result), expected_pages)
                    assert actual_text == expected_text, "Export changed source page text/order"

                metrics = page.evaluate("""()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth,
                  pageCount:document.querySelector('#page-total-indicator').textContent.trim(),
                  organizerCardCount:document.querySelectorAll('#organizer-grid .organizer-thumb-card').length,
                  longTasks:window.__longTasks||[],studioPhases:window.__studioPhases||[]})""")
                assert metrics["documentWidth"] <= metrics["width"], metrics
                assert metrics["organizerCardCount"] == expected_pages, metrics
                assert not errors, errors
                rounds.append({"round": round_no, "status": response.status,
                               "load_to_first_page_seconds": round(first_page_ready-started, 2),
                               "export_seconds": round(time.perf_counter()-export_started, 2),
                               "total_seconds": round(time.perf_counter()-started, 2),
                               "source_bytes": SOURCE.stat().st_size, "output_bytes": output_path.stat().st_size,
                               "page_count": len(actual_text), "page_text_and_order_preserved": True,
                               "organizer_cards_rendered": metrics["organizerCardCount"],
                               "select_all_and_invert_checked": all_cards_selected,
                               "single_page_slot_fallback_recreated": fallback_recreated,
                               "viewport": metrics["width"], "document_width": metrics["documentWidth"],
                               "long_tasks_over_50ms": metrics["longTasks"], "studio_phases": metrics["studioPhases"],
                               "page_errors": errors})
                context.close()
            browser.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()

report = {"fixture": str(SOURCE), "fixture_pages": expected_pages,
          "cpu_throttle_rate": float(os.environ.get("PAPERPLANE_CPU_THROTTLE", "4")),
          "slot_fallback_exercised": EXERCISE_SLOT_FALLBACK, "rounds": rounds, "verdict": "PASS"}
filename = "browser-id122-mobile-69page-studio-export.json" if EXERCISE_SLOT_FALLBACK else "browser-id122-mobile-69page-studio-perf.json"
(OUT / filename).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
