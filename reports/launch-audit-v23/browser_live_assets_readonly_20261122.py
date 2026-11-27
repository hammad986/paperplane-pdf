"""Read-only Chromium fingerprint of live Paperplane assets and health."""
from __future__ import annotations

import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
local_html = (ROOT / "web/index.html").read_text(encoding="utf-8")
local_assets = sorted(set(re.findall(
    r'(?:src|href)="([^"\s]*(?:app\.js|page_organizer\.js|styles\.css|pdf_runtime\.js)\?v=\d+)"',
    local_html,
)))

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors: list[str] = []
    response_records: list[dict] = []
    failures: list[dict] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("response", lambda response: response_records.append({"url": response.url, "status": response.status})
            if response.url.startswith(BASE) else None)
    page.on("requestfailed", lambda request: failures.append({"url": request.url, "error": request.failure}))
    navigation_status = None
    navigation_error = None
    try:
        response = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
        navigation_status = response.status if response else None
    except Exception as error:
        navigation_error = type(error).__name__
    live_assets = page.evaluate("""() => [...document.querySelectorAll('script[src],link[href]')]
      .map(node => node.src || node.href)
      .filter(url => /(?:app\\.js|page_organizer\\.js|styles\\.css|pdf_runtime\\.js)\\?v=\\d+/.test(url))
      .map(url => new URL(url).pathname + new URL(url).search).sort()""")
    asset_probes = []
    for asset in live_assets:
        try:
            r = page.request.get(BASE + asset, timeout=10000)
            asset_probes.append({"asset": asset, "status": r.status, "bytes": len(r.body()) if r.ok else None})
        except Exception as error:
            asset_probes.append({"asset": asset, "error": type(error).__name__})
    try:
        health = page.request.get(BASE + "/api/health", timeout=10000)
        health_status = health.status
        health_body = health.json() if health.ok else {"body": health.text()[:500]}
    except Exception as error:
        health_status = None
        health_body = {"error": type(error).__name__}
    overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
    browser.close()

report = {
    "site": BASE, "read_only": True, "navigation_status": navigation_status,
    "navigation_error": navigation_error, "responses": response_records, "request_failures": failures,
    "live_assets": live_assets, "local_candidate_assets": local_assets, "asset_probes": asset_probes,
    "api_health_status": health_status, "api_health": health_body,
    "horizontal_overflow_at_1366px": overflow, "page_errors": errors,
    "local_candidate_is_live": set(local_assets).issubset(set(live_assets)),
}
(ROOT / "reports/launch-audit-v23/browser-live-assets-readonly-2026-11-22.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(json.dumps(report, indent=2))
