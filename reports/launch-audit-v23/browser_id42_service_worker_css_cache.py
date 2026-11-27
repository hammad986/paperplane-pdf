"""Verify the installed offline shell caches the stylesheet the app requests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
APP_VERSION = int(re.search(r'/assets/app\.js\?v=(\d+)', (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')).group(1))
SHELL_VERSION = int(re.search(r"paperplane-shell-v(\d+)", (ROOT / 'web' / 'assets' / 'service-worker.js').read_text(encoding='utf-8')).group(1))
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def awaitless_reload(page, url):
    response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
    return response.status if response else None


reports = []
external_base = os.environ.get("PAPERPLANE_SW_TEST_BASE")
temporary_context = TemporaryDirectory(prefix="paperplane-id42-sw-cache-") if not external_base else None
app = None
try:
    if external_base:
        base = external_base.rstrip("/")
    else:
        app, base, _ = helper.start_server(Path(temporary_context.name) / "data")
    try:
        if not external_base:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane app failed to start")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_number in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="allow")
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base, wait_until="domcontentloaded", timeout=30000)
                assert response and response.status == 200
                page.evaluate("navigator.serviceWorker.ready")
                page.wait_for_function("!!navigator.serviceWorker.controller", timeout=15000)
                cache_state = page.evaluate("""async () => {
                  const names=await caches.keys();
                  const shell=names.find(name=>name==='paperplane-shell-v__SHELL__');
                  const cache=shell?await caches.open(shell):null;
                  const requests=cache?await cache.keys():[];
                  const cssRequest=requests.find(request=>new URL(request.url).pathname==='/assets/styles.css'
                    && new URL(request.url).search==='?v=54');
                  const appRequest=requests.find(request=>new URL(request.url).pathname==='/assets/app.js'
                    && new URL(request.url).search==='?v=__APP__');
                  const oldAppRequest=requests.find(request=>new URL(request.url).pathname==='/assets/app.js'
                    && new URL(request.url).search==='?v=__PREV__');
                  const staleRequest=requests.find(request=>new URL(request.url).pathname==='/assets/styles.css'
                    && new URL(request.url).search==='?v=51');
                  const cssResponse=cssRequest?await cache.match(cssRequest):null;
                  const appResponse=appRequest?await cache.match(appRequest):null;
                  const cssText=cssResponse?await cssResponse.text():'';
                  return {names,shell,cssCached:!!cssResponse,cssBytes:cssText.length,appCached:!!appResponse,
                    cssHasPhoneLayout:cssText.includes('#app-shell.ai-active .ai-doc-info-group { flex: 1 0 100%; width: 100%; }'),
                    staleStylesheetCached:!!staleRequest,oldAppCached:!!oldAppRequest};
                }""".replace("__SHELL__", str(SHELL_VERSION)).replace("__APP__", str(APP_VERSION)).replace("__PREV__", str(APP_VERSION - 1)))
                assert cache_state["shell"] == f"paperplane-shell-v{SHELL_VERSION}", cache_state
                assert cache_state["cssCached"] and cache_state["cssBytes"] > 10000, cache_state
                assert cache_state["cssHasPhoneLayout"], cache_state
                assert not cache_state["staleStylesheetCached"], cache_state
                assert cache_state["appCached"] and not cache_state["oldAppCached"], cache_state

                cdp = context.new_cdp_session(page)
                cdp.send("Network.enable")
                cdp.send("Network.emulateNetworkConditions", {
                    "offline": True, "latency": 0, "downloadThroughput": 0, "uploadThroughput": 0,
                })
                offline_response = awaitless_reload(page, base)
                offline_state = page.evaluate("""() => ({
                  url:location.pathname,
                  stylesheet:document.querySelector('link[rel=stylesheet]')?.getAttribute('href'),
                  sheetCount:document.styleSheets.length,
                  bodyWidth:document.body.scrollWidth,
                  viewport:innerWidth,
                  background:getComputedStyle(document.body).backgroundColor
                })""")
                assert offline_response == 200, offline_state
                assert offline_state["stylesheet"] == "/assets/styles.css?v=54", offline_state
                assert offline_state["sheetCount"] >= 1 and offline_state["bodyWidth"] <= offline_state["viewport"] + 1, offline_state
                assert not errors, errors
                reports.append({"round": round_number, "online_status": response.status,
                                "offline_status": offline_response, "cache": cache_state,
                                "offline": offline_state, "page_errors": errors})
                context.close()
            browser.close()
    finally:
        if app:
            app.terminate()
            app.wait(timeout=10)
finally:
    if temporary_context:
        temporary_context.cleanup()

result = {"base": base, "rounds": reports}
evidence_name = (f"browser-id42-service-worker-css-cache-docker-v{APP_VERSION}.json" if external_base
                 else "browser-id42-service-worker-css-cache.json")
(OUT / evidence_name).write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
