"""Verify the current versioned local app shell is served from cache offline."""
from pathlib import Path
import json
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

results = []
with TemporaryDirectory(prefix="paperplane-sw-v67-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(service_workers="allow", viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
                page.wait_for_timeout(1000)
                before = page.evaluate("""async()=>({caches:await caches.keys(),assets:await (async()=>{
                  const c=await caches.open('paperplane-shell-v67');return {
                    app:!!await c.match('/assets/app.js?v=133'),
                    css:!!await c.match('/assets/styles.css?v=56'),
                    organizer:!!await c.match('/assets/page_organizer.js?v=19')
                  }
                })()})""")
                context.set_offline(True)
                offline = page.goto(base + "/", wait_until="domcontentloaded", timeout=15000)
                loaded = page.evaluate("""()=>({controller:!!navigator.serviceWorker.controller,title:document.title,
                  appAsset:document.querySelector('script[src*="app.js"]')?.getAttribute('src'),
                  cssAsset:document.querySelector('link[rel="stylesheet"]')?.getAttribute('href'),
                  background:getComputedStyle(document.body).backgroundColor,
                  organizerScript:[...document.scripts].some(s=>s.src.endsWith('/assets/page_organizer.js?v=19'))})""")
                result = {"round": round_no, "before": before, "offline_navigation_status": offline.status if offline else None,
                          "offline_page": loaded, "page_errors": errors}
                results.append(result)
                assert "paperplane-shell-v67" in before["caches"] and all(before["assets"].values()), result
                assert loaded["controller"] and loaded["appAsset"] == "/assets/app.js?v=133" and loaded["cssAsset"] == "/assets/styles.css?v=56" and loaded["organizerScript"] and not errors, result
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"rounds": results}
out = ROOT / "reports" / "launch-audit-v23" / "browser-id357-service-worker-v67-offline-local.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
