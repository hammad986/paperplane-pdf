"""Measure what triggers repeated mobile Studio toolbar geometry reads."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("C:/Users/mdham/Downloads/notes.pdf")
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id122-toolbar-cause-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3,
                                         is_mobile=True, has_touch=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            cdp = context.new_cdp_session(page)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            page.goto(f"{base}/studio", wait_until="domcontentloaded", timeout=30000)
            page.evaluate("""() => {
              const audit = window.__toolbarGeometryCause = { reads: [], resizes: [], longTasks: [] };
              new PerformanceObserver(list => audit.longTasks.push(...list.getEntries().map(entry => ({
                start: entry.startTime, duration: entry.duration
              })))).observe({type:'longtask', buffered:true});
              const nativeRect = Element.prototype.getBoundingClientRect;
              Element.prototype.getBoundingClientRect = function() {
                if (this.id === 'studio-toolbar') {
                  audit.reads.push({time: performance.now(), width: document.documentElement.clientWidth,
                    stack: new Error().stack?.split('\\n').slice(1, 7).map(line => line.trim())});
                }
                return nativeRect.call(this);
              };
              window.addEventListener('resize', () => audit.resizes.push({time: performance.now(),
                width: document.documentElement.clientWidth, height: document.documentElement.clientHeight,
                innerWidth, innerHeight}), {passive:true});
              const originalSync = window.syncStudioBatchPanelLocation;
              if (originalSync) window.syncStudioBatchPanelLocation = function(...args) {
                audit.batchSyncs = (audit.batchSyncs || 0) + 1;
                return originalSync.apply(this, args);
              };
            }""")
            page.locator("#studio-file-input").set_input_files(str(SOURCE))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true", timeout=90000)
            if page.locator("#studio-mobile-pages-btn").is_visible() and page.locator("#studio-mobile-pages-btn").get_attribute("aria-expanded") != "true":
                page.locator("#studio-mobile-pages-btn").click()
            page.wait_for_function("document.querySelector('#organizer-grid .organizer-thumb-card[data-page=\"1\"] .thumb-rendered-img')", timeout=30000)
            page.wait_for_timeout(400)
            result = page.evaluate("""() => ({...window.__toolbarGeometryCause,
              screen: {width: innerWidth, height: innerHeight, dpr: devicePixelRatio},
              errors: []})""")
            result["errors"] = errors
            result["fixture"] = str(SOURCE)
            result["page_count"] = 69
            result["window_resize_count"] = len(result.get("resizes", []))
            result["toolbar_rect_read_count"] = len(result.get("reads", []))
            output = ROOT / "reports" / "launch-audit-v23" / "browser-id122-studio-toolbar-sync-cause.json"
            output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps({key: value for key, value in result.items() if key not in {"reads", "resizes"}}, indent=2))
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)
