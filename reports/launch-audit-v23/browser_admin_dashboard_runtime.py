"""Exercise the production-mode admin revenue dashboard at desktop and mobile widths."""
from __future__ import annotations

import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
BASE = os.environ["PAPERPLANE_TEST_BASE"].rstrip("/")
ADMIN_TOKEN = os.environ["PAPERPLANE_TEST_ADMIN_SESSION"]

results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for round_no, width in enumerate((1440, 390, 320), start=1):
        page = browser.new_page(viewport={"width": width, "height": 1000})
        page.add_init_script("window.__adminXss = 0")
        page.add_init_script(
            "sessionStorage.setItem('pp_admin_session'," + json.dumps(ADMIN_TOKEN) + ")"
        )
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def hostile_revenue(route):
            response = route.fetch()
            payload = response.json()
            payload.setdefault("recent_transactions", []).append({
                "email": "injected@example.test",
                "tier": "pro",
                "order_id": "xss-probe",
                "amount": '0<img id="pp-admin-amount-xss" src="x" onerror="window.__adminXss++">',
                "gateway_environment": "UNKNOWN",
                "created_at": 1,
                "status": "Paid",
            })
            route.fulfill(response=response, json=payload)

        page.route("**/api/admin/revenue", hostile_revenue)
        page.goto(BASE + "/admin", wait_until="domcontentloaded")
        page.locator("#tab-revenue-btn").wait_for(state="visible")
        page.locator("#tab-revenue-btn").click()
        page.wait_for_function(
            "document.querySelector('#rev-gross-revenue')?.textContent.trim() !== '-'",
            timeout=20000,
        )

        snapshot = page.evaluate("""() => ({
          width: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          chartWidth: document.querySelector('#bar-chart-container').clientWidth,
          chartScrollWidth: document.querySelector('#bar-chart-container').scrollWidth,
          tableRegion: [...document.querySelectorAll('.table-container')].some(
            item => item.getAttribute('aria-label') === 'Paying customers and recent transactions'
              && item.tabIndex === 0 && item.getAttribute('role') === 'region'
          ),
          xssNodeCount: document.querySelectorAll('#pp-admin-amount-xss').length,
          amountText: document.querySelector('#revenue-tbody tr:last-child td:nth-child(4)').textContent.trim(),
          scriptCount: window.__adminXss,
        })""")
        assert snapshot["documentWidth"] <= width, snapshot
        assert snapshot["chartWidth"] > 0 and snapshot["chartScrollWidth"] >= snapshot["chartWidth"], snapshot
        assert snapshot["tableRegion"], snapshot
        assert snapshot["xssNodeCount"] == 0 and snapshot["scriptCount"] == 0, snapshot
        assert snapshot["amountText"] == "₹0", snapshot
        assert not errors, errors
        if width <= 390:
            page.locator("#bar-chart-container").focus()
            assert page.evaluate("document.activeElement.id === 'bar-chart-container'")
        screenshot = OUT / f"browser-admin-dashboard-{width}px-docker.png"
        page.screenshot(path=str(screenshot), full_page=True)
        results.append({
            "round": round_no,
            **snapshot,
            "page_errors": errors,
            "screenshot": str(screenshot),
        })
        page.close()
    browser.close()

evidence = OUT / "browser-admin-dashboard-runtime.json"
evidence.write_text(json.dumps({"passed": True, "rounds": results}, indent=2), encoding="utf-8")
print(json.dumps({"passed": True, "viewports": [item["width"] for item in results],
                  "evidence": str(evidence)}, indent=2))
