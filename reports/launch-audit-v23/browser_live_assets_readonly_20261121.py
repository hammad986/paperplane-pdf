"""Read-only real-Chromium fingerprint of the deployed Paperplane candidate."""
from __future__ import annotations

import json
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
local_html = (ROOT / "web/index.html").read_text(encoding="utf-8")
local_assets = sorted(set(re.findall(
    r'(?:src|href)="([^"]*(?:app\.js|page_organizer\.js|styles\.css|pdf_runtime\.js)\?v=\d+)"',
    local_html,
)))

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors = []
    responses = []
    request_failures = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("response", lambda response: responses.append({"url": response.url, "status": response.status})
            if response.url.startswith(BASE) else None)
    page.on("requestfailed", lambda request: request_failures.append({"url": request.url, "error": request.failure}))
    response = None
    navigation_error = None
    try:
        response = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    except Exception as error:
        navigation_error = type(error).__name__
    live_assets = page.evaluate("""() => [...document.querySelectorAll('script[src],link[href]')]
      .map(node => node.src || node.href)
      .filter(url => /(?:app\\.js|page_organizer\\.js|styles\\.css|pdf_runtime\\.js)\\?v=\\d+/.test(url))
      .map(url => new URL(url).pathname + new URL(url).search).sort()""")
    app_asset_probe = None
    app_probe_error = None
    try:
        app_asset_probe = page.request.get(BASE + "/assets/app.js?v=91", timeout=10000)
    except Exception as error:
        app_probe_error = type(error).__name__
    try:
        health_response = page.request.get(BASE + "/api/health", timeout=8000)
        health_status = health_response.status
        try:
            health_body = health_response.json()
        except Exception:
            health_body = {"body": health_response.text()[:500]}
    except Exception as error:
        health_status = None
        health_body = {"error": type(error).__name__}
    overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
    browser.close()

report = {
    "site": BASE,
    "read_only": True,
    "http_status": response.status if response else None,
    "navigation_error": navigation_error,
    "responses": responses,
    "request_failures": request_failures,
    "app_asset_direct_probe_status": app_asset_probe.status if app_asset_probe else None,
    "app_asset_direct_probe_error": app_probe_error,
    "live_assets": live_assets,
    "local_candidate_assets": local_assets,
    "api_health_status": health_status,
    "api_health": health_body,
    "horizontal_overflow_at_1366px": overflow,
    "page_errors": errors,
    "local_candidate_is_live": set(local_assets).issubset(set(live_assets)),
}
(ROOT / "reports/launch-audit-v23/browser-live-assets-readonly-2026-11-21.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(json.dumps(report, indent=2))
