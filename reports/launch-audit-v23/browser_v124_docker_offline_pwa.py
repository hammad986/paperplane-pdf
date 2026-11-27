"""Verify current production image PWA shell survives offline navigation in Chromium."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:18503"
rounds = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for round_no in (1, 2):
        context = browser.new_context(
            service_workers="allow", viewport={"width": 390, "height": 844},
            is_mobile=True, has_touch=True,
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        first = page.goto(BASE + "/studio", wait_until="domcontentloaded", timeout=30000)
        assert first and first.status == 200
        page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=20000)
        page.wait_for_timeout(1200)
        before = page.evaluate("""async()=>{
          const cache=await caches.open('paperplane-shell-v57');
          return {caches:await caches.keys(),assets:{app:!!await cache.match('/assets/app.js?v=124'),
            css:!!await cache.match('/assets/styles.css?v=56'),
            organizer:!!await cache.match('/assets/page_organizer.js?v=16')}}
        }""")
        assert "paperplane-shell-v57" in before["caches"] and all(before["assets"].values()), before
        context.set_offline(True)
        offline = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=20000)
        loaded = page.evaluate("""()=>({controller:!!navigator.serviceWorker.controller,title:document.title,
          app:document.querySelector('script[src*="app.js"]')?.getAttribute('src'),
          css:document.querySelector('link[rel="stylesheet"]')?.getAttribute('href'),
          organizer:[...document.scripts].some(s=>s.src.endsWith('/assets/page_organizer.js?v=16')),
          bodyWidth:document.body.scrollWidth,documentWidth:document.documentElement.scrollWidth,
          viewportWidth:innerWidth,background:getComputedStyle(document.body).backgroundColor})""")
        result={"round":round_no,"cache":before,"offline_status":offline.status if offline else None,
                "offline_page":loaded,"page_errors":errors}
        rounds.append(result)
        assert offline and offline.status == 200, result
        assert loaded["controller"] and loaded["app"] == "/assets/app.js?v=124", result
        assert loaded["css"] == "/assets/styles.css?v=56" and loaded["organizer"], result
        assert loaded["bodyWidth"] <= 392 and loaded["documentWidth"] <= 392, result
        assert not errors, result
        context.close()
    browser.close()

evidence={"runtime":"production-mode Docker image paperplane-v23-audit:codex-v124",
          "image_id":"sha256:a5df4a859eed7a2969ef601a43cb783169eadde1d33b41e322406070022d2fde",
          "offline_rounds":rounds}
out=ROOT/"reports"/"launch-audit-v23"/"browser-v124-docker-offline-pwa.json"
out.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
print(json.dumps(evidence,indent=2))
