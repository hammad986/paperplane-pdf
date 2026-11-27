"""Assert mobile Studio reuses toolbar geometry and stays aligned after resizes."""
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
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id122-toolbar-geometry-") as temporary:
    data_dir = Path(temporary) / "data"
    fixture = Path(temporary) / "toolbar-geometry.pdf"
    with fitz.open() as document:
        for page_num in range(1, 5):
            page = document.new_page(width=595, height=842)
            page.insert_text((72, 90), f"STUDIO TOOLBAR GEOMETRY BATCHING PAGE {page_num}")
        document.save(fixture)

    app, base, _ = helper.start_server(data_dir)
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(120):
            if app.poll() is not None:
                raise RuntimeError(f"Local server exited: {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("Local app failed to start")

        evidence = {"viewport": {"width": 390, "height": 844}, "rounds": []}
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport=evidence["viewport"], is_mobile=True,
                                              device_scale_factor=2, has_touch=True)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='4' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=30000)
                page.evaluate("""() => {
                  const native = HTMLElement.prototype.getBoundingClientRect;
                  window.__toolbarGeometryReads = 0;
                  HTMLElement.prototype.getBoundingClientRect = function(...args) {
                    if (new Error().stack?.includes('syncStudioMobilePagesPanelPosition')) {
                      window.__toolbarGeometryReads++;
                    }
                    return native.apply(this, args);
                  };
                }""")

                page.evaluate("""() => document.querySelector('#btn-mode-annotate').click()""")
                page.wait_for_timeout(50)
                annotate_reads = page.evaluate("window.__toolbarGeometryReads")
                annotate_top = page.locator("#studio-thumbnails-bar").evaluate(
                    "element => getComputedStyle(element).getPropertyValue('--studio-mobile-pages-top').trim()"
                )
                assert annotate_reads == 0, {"mode": "annotate", "geometry_reads": annotate_reads}

                page.evaluate("""() => {window.__toolbarGeometryReads=0; document.querySelector('#btn-mode-organize').click();}""")
                page.wait_for_timeout(50)
                organize_reads = page.evaluate("window.__toolbarGeometryReads")
                organize_top = page.locator("#studio-thumbnails-bar").evaluate(
                    "element => getComputedStyle(element).getPropertyValue('--studio-mobile-pages-top').trim()"
                )
                assert organize_reads == 0, {"mode": "organize", "geometry_reads": organize_reads}
                assert annotate_top.endswith("px") and organize_top.endswith("px"), (annotate_top, organize_top)

                resized_tops = {}
                for width in (820, 683):
                    page.set_viewport_size({"width": width, "height": 844})
                    page.wait_for_timeout(80)
                    measured = page.evaluate("""() => ({
                      variable: getComputedStyle(document.querySelector('#studio-thumbnails-bar')).getPropertyValue('--studio-mobile-pages-top').trim(),
                      expected: `${Math.max(68, Math.ceil(document.querySelector('#studio-toolbar').getBoundingClientRect().bottom + 8))}px`
                    })""")
                    assert measured["variable"] == measured["expected"], {"width": width, **measured}
                    resized_tops[str(width)] = measured["variable"]

                # Bulk selection and subsequent checkbox updates keep the batch
                # toolbar visible; they must not remeasure unrelated toolbar geometry.
                page.locator("#org-select-all-btn").click()
                page.evaluate("window.__toolbarGeometryReads=0")
                for page_num in (1, 2, 3):
                    page.locator(f'.organizer-thumb-card[data-page="{page_num}"] .thumb-checkbox-label').click()
                selection_reads = page.evaluate("window.__toolbarGeometryReads")
                assert selection_reads == 0, {"selection_geometry_reads": selection_reads}

                # Hiding the bar must reuse cached toolbar geometry as well.
                page.evaluate("window.__toolbarGeometryReads=0")
                page.locator("#batch-clear-btn").click()
                clear_reads = page.evaluate("window.__toolbarGeometryReads")
                assert clear_reads == 0, {"clear_geometry_reads": clear_reads}

                page.set_viewport_size({"width": 320, "height": 225})
                page.wait_for_timeout(100)
                short_viewport = page.evaluate("""() => {
                  const panel = document.querySelector('#studio-thumbnails-bar');
                  const rect = panel.getBoundingClientRect();
                  return {
                    width: document.documentElement.scrollWidth,
                    viewport: innerWidth,
                    visible: getComputedStyle(panel).display !== 'none' && rect.height > 0,
                    top: Math.ceil(rect.top),
                    height: Math.floor(rect.height),
                    bottom: Math.ceil(rect.bottom),
                    topVariable: getComputedStyle(panel).getPropertyValue('--studio-mobile-pages-top').trim(),
                    pageOneThumbnail: !!document.querySelector('.organizer-thumb-card[data-page="1"] .thumb-rendered-img')
                  };
                }""")
                assert short_viewport["width"] == short_viewport["viewport"] == 320, short_viewport
                assert short_viewport["visible"] and short_viewport["top"] <= 70 and short_viewport["height"] >= 80, short_viewport
                assert short_viewport["bottom"] <= 225 and short_viewport["pageOneThumbnail"], short_viewport
                dimensions = page.evaluate("({width:document.documentElement.scrollWidth,viewport:innerWidth})")
                evidence["rounds"].append({"round": round_no, "annotate_geometry_reads": annotate_reads,
                                           "organize_geometry_reads": organize_reads,
                                           "selection_geometry_reads": selection_reads,
                                           "clear_geometry_reads": clear_reads,
                                           "resized_pages_tops": resized_tops,
                                           "short_viewport_320x225": short_viewport,
                                           "annotate_pages_top": annotate_top, "organize_pages_top": organize_top,
                                           "document_dimensions": dimensions})
                context.close()
            browser.close()

        assert not errors, errors
        evidence["page_errors"] = errors
        evidence["verdict"] = "PASS"
        path = OUT / "browser-id122-toolbar-geometry-batching.json"
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=8)
