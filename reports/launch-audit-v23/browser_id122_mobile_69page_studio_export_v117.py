"""Low-end mobile-emulation test for opening and exporting a real 69-page PDF in Studio."""
from __future__ import annotations

import base64
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
EVIDENCE_SUFFIX = os.environ.get("PAPERPLANE_EVIDENCE_SUFFIX", "")
FORCE_DEVICE_PIXEL_RATIO = float(os.environ.get("PAPERPLANE_TEST_FORCE_DPR", "0"))
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
            desktop_scale_probe = None
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True,
                                              has_touch=True, accept_downloads=True)
                if FORCE_DEVICE_PIXEL_RATIO > 0:
                    context.add_init_script(
                        f"Object.defineProperty(window, 'devicePixelRatio', {{get: () => {FORCE_DEVICE_PIXEL_RATIO}}});"
                    )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                cdp = context.new_cdp_session(page)
                throttle_rate = float(os.environ.get("PAPERPLANE_CPU_THROTTLE", "4"))
                cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle_rate})
                cdp.send("Profiler.enable")
                cdp.send("Profiler.setSamplingInterval", {"interval": 500})
                page.add_init_script("""window.__longTasks=[];new PerformanceObserver(list=>
                  window.__longTasks.push(...list.getEntries().map(e=>({duration:e.duration,start:e.startTime,
                    attribution:[...(e.attribution||[])].map(a=>({containerType:a.containerType,containerName:a.containerName,containerSrc:a.containerSrc}))})))
                ).observe({type:'longtask',buffered:true});""")

                started = time.perf_counter()
                response = page.goto(f"{base}/studio", wait_until="domcontentloaded", timeout=30000)
                assert response and response.status == 200
                cdp.send("Profiler.start")
                page.evaluate("""()=>{
                  window.__studioPhases=[];
                  window.__studioRenderEvents=[];
                  const renderPage=window.renderStudioPage;
                  if(renderPage){
                    window.renderStudioPage=async function(pageNum,options={}){
                      const started=performance.now();
                      const event={page:Number(pageNum),started,priority:!!options.priority};
                      window.__studioRenderEvents.push(event);
                      try { return await renderPage.call(this,pageNum,options); }
                      finally { event.duration=performance.now()-started; event.ended=performance.now(); }
                    };
                  }
                  const organizer=window.PaperplanePageOrganizer;
                  if(organizer){
                    window.__thumbnailActive=0;
                    window.__thumbnailPeak=0;
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
                      window.__thumbnailActive++;
                      window.__thumbnailPeak=Math.max(window.__thumbnailPeak,window.__thumbnailActive);
                      try {
                        const result=await renderCard(card,pageNum);
                        window.__studioPhases.push({phase:'thumbnail-page',page:pageNum,duration:performance.now()-started});
                        return result;
                      } finally { window.__thumbnailActive--; }
                    };
                  }
                }""")
                page.locator("#studio-file-input").set_input_files(str(SOURCE))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
                mobile_pages = page.locator("#studio-mobile-pages-btn")
                if mobile_pages.is_visible() and mobile_pages.get_attribute("aria-expanded") != "true":
                    mobile_pages.click()
                same_page_check = page.evaluate("""() => {
                  const editor = window.PaperplaneEditor;
                  editor.selection.select('same-page-selection-probe');
                  let calls = 0;
                  const original = editor.onPageRendered;
                  editor.onPageRendered = function(...args) { calls++; return original.apply(this, args); };
                  try {
                    setActiveStudioPage(state.studio.currentPage, {scrollThumbnail: false});
                    return { selectionPreserved: editor.selection.isSelected('same-page-selection-probe'), reattachments: calls };
                  } finally { editor.onPageRendered = original; editor.selection.deselect(); }
                }""")
                assert same_page_check == {"selectionPreserved": True, "reattachments": 0}, same_page_check
                page.wait_for_function("document.querySelectorAll('#organizer-grid .organizer-thumb-card').length === 69", timeout=30000)
                try:
                    page.wait_for_function("document.querySelector('.organizer-thumb-card[data-page=\"1\"] .thumb-rendered-img')", timeout=30000)
                except Exception as error:
                    thumbnail_diagnostics = page.evaluate("""() => {
                      const card = document.querySelector('.organizer-thumb-card[data-page="1"]');
                      const root = document.querySelector('#studio-thumbnails-container');
                      const organizer = window.PaperplanePageOrganizer;
                      return {
                        cardConnected: !!card?.isConnected,
                        cardRect: card?.getBoundingClientRect().toJSON(),
                        rootRect: root?.getBoundingClientRect().toJSON(),
                        rootOverflowY: root ? getComputedStyle(root).overflowY : null,
                        studioPagesExpanded: document.querySelector('#studio-pages-toggle-btn')?.getAttribute('aria-expanded'),
                        observer: !!organizer?.observer,
                        queueLength: organizer?.thumbnailRenderQueue?.length,
                        active: organizer?.thumbnailRenderActive,
                        scheduled: organizer?.thumbnailRenderQueueScheduled,
                        pageObjectReady: !!organizer?.pdfDoc,
                        preview: card?.querySelector('.thumb-preview-wrap')?.innerHTML,
                      };
                    }""")
                    raise AssertionError(f"Studio page 1 thumbnail did not render: {thumbnail_diagnostics}") from error
                page_one_thumbnail_rendered = True
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
                first_page_ready_browser_ms = page.evaluate("performance.now()")
                profile = cdp.send("Profiler.stop")["profile"]
                frame_by_id = {node["id"]: node.get("callFrame", {}) for node in profile.get("nodes", [])}
                profile_counts = {}
                for node_id in profile.get("samples", []):
                    frame = frame_by_id.get(node_id, {})
                    label = f"{frame.get('functionName') or '(anonymous)'} @ {frame.get('url') or '[native]'}"
                    profile_counts[label] = profile_counts.get(label, 0) + 1
                cpu_profile_hotspots = [{"samples": count, "frame": label}
                                        for label, count in sorted(profile_counts.items(), key=lambda item: item[1], reverse=True)[:25]]
                cdp.send("Profiler.disable")
                canvas_locator = page.locator('.studio-page-sheet[data-page="1"] .pdf-page-canvas')
                canvas_locator.screenshot(path=str(OUT / f"id122-dpr15-page1{EVIDENCE_SUFFIX}-round{round_no}.png"))
                canvas_data_url = canvas_locator.evaluate("canvas => canvas.toDataURL('image/png')")
                canvas_png = base64.b64decode(canvas_data_url.split(',', 1)[1])
                (OUT / f"id122-dpr15-page1-canvas{EVIDENCE_SUFFIX}-round{round_no}.png").write_bytes(canvas_png)
                visible_pixel_count = canvas_locator.evaluate("""canvas => {
                  const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
                  let count=0;
                  for(let i=0;i<pixels.length;i+=4) if(pixels[i]<235||pixels[i+1]<235||pixels[i+2]<235) count++;
                  return count;
                }""")
                assert visible_pixel_count > 100, f"Page 1 canvas looks blank ({visible_pixel_count} non-white pixels)"
                page.evaluate("""()=>{
                  window.__countStudioSlotRects=false;
                  window.__studioSlotRectReads=0;
                  const original=Element.prototype.getBoundingClientRect;
                  Element.prototype.getBoundingClientRect=function(){
                    if(window.__countStudioSlotRects && this.matches?.('.studio-page-sheet')) window.__studioSlotRectReads++;
                    return original.apply(this,arguments);
                  };
                  window.__countStudioSlotRects=true;
                }""")
                page.locator('.studio-page-sheet[data-page="40"]').scroll_into_view_if_needed()
                page.wait_for_function("state.studio.currentPage >= 39 && state.studio.currentPage <= 41", timeout=30000)
                page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"40\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
                page.wait_for_function("document.querySelector('.organizer-thumb-card[data-page=\"40\"] .thumb-rendered-img')", timeout=30000)
                page_forty_thumbnail_rendered = True
                scroll_rect_reads = page.evaluate("()=>{window.__countStudioSlotRects=false;return window.__studioSlotRectReads}")
                assert scroll_rect_reads < 20, f"Page scroll measured {scroll_rect_reads} slots; expected logarithmic lookup"
                page.locator('.studio-page-sheet[data-page="1"]').scroll_into_view_if_needed()
                page.wait_for_function("state.studio.currentPage === 1", timeout=30000)
                page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'", timeout=30000)
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

                metrics = page.evaluate("""readyAt=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth,
                  devicePixelRatio,
                  pageCount:document.querySelector('#page-total-indicator').textContent.trim(),
                  activeCanvas: (()=>{const canvas=document.querySelector('.studio-page-sheet[data-page="1"] .pdf-page-canvas');
                    return canvas?{width:canvas.width,height:canvas.height,cssWidth:canvas.style.width,cssHeight:canvas.style.height}:null})(),
                  organizerCardCount:document.querySelectorAll('#organizer-grid .organizer-thumb-card').length,
                  longTasks:window.__longTasks||[],
                  longTasksBeforeFirstPage:(window.__longTasks||[]).filter(task=>task.start+task.duration<=readyAt),
                  studioPhases:window.__studioPhases||[],
                  thumbnailPeakConcurrency:window.__thumbnailPeak||0,
                  studioRenderEvents:window.__studioRenderEvents||[]})""", first_page_ready_browser_ms)
                assert metrics["documentWidth"] <= metrics["width"], metrics
                assert metrics["organizerCardCount"] == expected_pages, metrics
                canvas_scale = metrics["activeCanvas"]["width"] / int(metrics["activeCanvas"]["cssWidth"].removesuffix("px"))
                assert 1 <= canvas_scale <= 1.51, {"devicePixelRatio": metrics["devicePixelRatio"],
                                                    "canvasScale": canvas_scale, "canvas": metrics["activeCanvas"]}
                assert not errors, errors
                rounds.append({"round": round_no, "status": response.status,
                               "load_to_first_page_seconds": round(first_page_ready-started, 2),
                               "export_seconds": round(time.perf_counter()-export_started, 2),
                               "total_seconds": round(time.perf_counter()-started, 2),
                               "source_bytes": SOURCE.stat().st_size, "output_bytes": output_path.stat().st_size,
                               "page_count": len(actual_text), "page_text_and_order_preserved": True,
                               "organizer_cards_rendered": metrics["organizerCardCount"],
                               "page_one_thumbnail_rendered": page_one_thumbnail_rendered,
                               "page_forty_thumbnail_rendered": page_forty_thumbnail_rendered,
                               "select_all_and_invert_checked": all_cards_selected,
                               "same_page_selection_check": same_page_check,
                               "single_page_slot_fallback_recreated": fallback_recreated,
                               "scroll_to_page_40_then_back": True,
                               "studio_page_slot_rect_reads_for_scroll": scroll_rect_reads,
                               "viewport": metrics["width"], "document_width": metrics["documentWidth"],
                               "device_pixel_ratio": metrics["devicePixelRatio"], "active_canvas": metrics["activeCanvas"],
                               "active_canvas_scale": round(canvas_scale, 3),
                               "active_page_nonwhite_pixels": visible_pixel_count,
                               "long_tasks_over_50ms": metrics["longTasks"],
                               "long_tasks_before_first_page": metrics["longTasksBeforeFirstPage"],
                               "studio_phases": metrics["studioPhases"],
                               "thumbnail_peak_concurrency": metrics["thumbnailPeakConcurrency"],
                               "studio_render_events": metrics["studioRenderEvents"],
                               "cpu_profile_hotspots": cpu_profile_hotspots,
                               "page_errors": errors})
                context.close()
            desktop_context = browser.new_context(viewport={"width": 1366, "height": 900}, device_scale_factor=3,
                                                  accept_downloads=True)
            desktop_page = desktop_context.new_page()
            desktop_errors = []
            desktop_page.on("pageerror", lambda error: desktop_errors.append(str(error)))
            desktop_page.goto(f"{base}/studio", wait_until="domcontentloaded", timeout=30000)
            desktop_page.locator("#studio-file-input").set_input_files(str(SOURCE))
            desktop_page.wait_for_function(
                "document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && "
                "document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000
            )
            desktop_page.wait_for_function(
                "document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'",
                timeout=30000,
            )
            desktop_scale_probe = desktop_page.evaluate("""()=>{
              const canvas=document.querySelector('.studio-page-sheet[data-page="1"] .pdf-page-canvas');
              return {devicePixelRatio, width:canvas.width, cssWidth:parseInt(canvas.style.width,10),
                canvasScale:canvas.width/parseInt(canvas.style.width,10)};
            }""")
            assert desktop_scale_probe["devicePixelRatio"] == 3 and 1.99 <= desktop_scale_probe["canvasScale"] <= 2.01, desktop_scale_probe
            assert not desktop_errors, desktop_errors
            desktop_context.close()
            browser.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()

report = {"fixture": str(SOURCE), "fixture_pages": expected_pages,
          "cpu_throttle_rate": float(os.environ.get("PAPERPLANE_CPU_THROTTLE", "4")),
          "slot_fallback_exercised": EXERCISE_SLOT_FALLBACK, "rounds": rounds,
          "desktop_dpr3_scale_probe": desktop_scale_probe, "verdict": "PASS"}
filename = (f"browser-id122-mobile-69page-studio-export{EVIDENCE_SUFFIX}.json" if EXERCISE_SLOT_FALLBACK else f"browser-id122-mobile-69page-studio-perf{EVIDENCE_SUFFIX}.json")
if EVIDENCE_SUFFIX:
    filename = f"{Path(filename).stem}{EVIDENCE_SUFFIX}{Path(filename).suffix}"
(OUT / filename).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
