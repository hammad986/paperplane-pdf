"""Verify the current production-image shell is cached and usable offline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = os.environ.get("PAPERPLANE_DOCKER_BASE", "http://127.0.0.1:18502")
index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
worker_source = (ROOT / "web" / "assets" / "service-worker.js").read_text(encoding="utf-8")
app_asset = re.search(r'/assets/app\.js\?v=\d+', index_html).group(0)
cache_name = re.search(r"const CACHE_NAME = '([^']+)'", worker_source).group(1)
assert f"'{app_asset}'" in worker_source
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
        cached = page.evaluate("""async cacheName=>{
          const cache=await caches.open(cacheName);
          const keys=await cache.keys();
          return {caches:await caches.keys(),assets:keys.map(request=>new URL(request.url).pathname+new URL(request.url).search)};
        }""", cache_name)
        assert cache_name in cached["caches"] and app_asset in cached["assets"], cached
        context.set_offline(True)
        offline = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=20000)
        loaded = page.evaluate("""()=>({controller:!!navigator.serviceWorker.controller,title:document.title,
          app:document.querySelector('script[src*="app.js"]')?.getAttribute('src'),
          css:document.querySelector('link[rel="stylesheet"]')?.getAttribute('href'),
          bodyWidth:document.body.scrollWidth,documentWidth:document.documentElement.scrollWidth,
          viewportWidth:innerWidth,background:getComputedStyle(document.body).backgroundColor})""")
        result = {"round": round_no, "cached_shell": cached, "offline_status": offline.status if offline else None,
                  "offline_page": loaded, "page_errors": errors}
        rounds.append(result)
        assert offline and offline.status == 200, result
        assert loaded["controller"] and loaded["app"] == app_asset, result
        assert loaded["bodyWidth"] <= 392 and loaded["documentWidth"] <= 392, result
        assert not errors, result
        context.close()
    browser.close()

image_id = os.environ.get("PAPERPLANE_DOCKER_IMAGE_ID", "not-supplied")
evidence = {"runtime": "production-mode Docker image", "image_id": image_id,
            "cache_name": cache_name, "app_asset": app_asset, "offline_rounds": rounds}
out = OUT / "browser-v130-docker-offline-pwa.json"
out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
