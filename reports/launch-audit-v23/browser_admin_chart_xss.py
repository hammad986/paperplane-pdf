"""Browser regression: hostile chart labels/counts remain inert admin text."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

MARKER = "__paperplane_admin_chart_xss"
payload = {
    "status": "ok",
    "environment": "test",
    "total_users": 1,
    "new_signups_7d": 0,
    "pro_users": 0,
    "dev_users": 0,
    "free_users": 1,
    "today_active": 0,
    "total_waitlist": 0,
    "total_jobs": 0,
    "jobs_today": 0,
    "tier_breakdown": {"free": 1},
    "days_trend": [
        {
            "date": f'"><img src=x onerror="window.{MARKER}=true">',
            "count": f'1<img src=x onerror="window.{MARKER}=true">',
        }
    ],
    "recent_audits": [],
}

with TemporaryDirectory(prefix="paperplane-admin-chart-xss-") as temporary:
    process, base, identity = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            context.add_init_script(
                "sessionStorage.setItem('pp_admin_session', " + json.dumps(identity["admin"]) + ");"
                + f"window.{MARKER}=false;"
            )

            async_payloads = {
                "/api/admin/auth/status": {"locked": False},
                "/api/admin/dashboard": payload,
                "/api/admin/users": {"users": []},
                "/api/admin/waitlist": {"entries": []},
                "/api/admin/revenue": {"recent_transactions": []},
                "/api/admin/ai-config": {"config": {}},
                "/api/admin/ai-health": {"status": "ok"},
                "/api/admin/feedback": {"feedback": []},
                "/api/admin/sessions": {"sessions": []},
            }

            def fulfill_admin(route):
                path = route.request.url.removeprefix(base)
                response = async_payloads.get(path, {"status": "ok", "items": []})
                route.fulfill(status=200, content_type="application/json", body=json.dumps(response))

            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.route("**/api/admin/**", fulfill_admin)
            response = page.goto(base + "/admin", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.querySelector('#bar-chart-container .bar-label')?.textContent.includes('<img')",
                timeout=10000,
            )
            result = page.evaluate(
                """marker => {
                  const chart = document.querySelector('#bar-chart-container');
                  const label = chart?.querySelector('.bar-label');
                  const bar = chart?.querySelector('.bar-fill');
                  return {
                    adminScript: [...document.scripts].find(script => script.src.includes('/assets/admin.js'))?.src,
                    labelText: label?.textContent,
                    labelElementCount: label?.querySelectorAll('*').length ?? -1,
                    barTitle: bar?.getAttribute('title'),
                    barHeight: bar?.style.height,
                    injectedImages: chart?.querySelectorAll('img').length ?? -1,
                    markerExecuted: window[marker],
                  };
                }""",
                MARKER,
            )
            assert response and response.status == 200
            assert result["injectedImages"] == 0, result
            assert result["labelElementCount"] == 0, result
            assert result["markerExecuted"] is False, result
            assert result["barHeight"] == "6%", result
            assert result["adminScript"].endswith("/assets/admin.js?v=18"), result
            assert not page_errors, page_errors

            layouts = []
            for width in (320, 390, 820, 1366):
                page.set_viewport_size({"width": width, "height": 844})
                layout = page.evaluate("""() => ({
                  viewport: innerWidth,
                  documentWidth: document.documentElement.scrollWidth,
                  bodyWidth: document.body.scrollWidth,
                  chartWidth: document.querySelector('#bar-chart-container')?.clientWidth ?? 0,
                  chartScrollWidth: document.querySelector('#bar-chart-container')?.scrollWidth ?? 0,
                })""")
                layouts.append(layout)
                assert layout["documentWidth"] <= width + 2, layout
                assert layout["bodyWidth"] <= width + 2, layout
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except Exception:
            process.kill()

evidence = {
    "runtime": "local Chromium against isolated current-source server",
    "synthetic_payload_only": True,
    "checks": result,
    "responsive_layouts": layouts,
    "page_errors": page_errors,
}
target = ROOT / "reports" / "launch-audit-v23" / "browser-admin-chart-xss.json"
target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(json.dumps(evidence, indent=2))
