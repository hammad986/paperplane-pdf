"""Render the Admin AI health panel against controlled local health responses."""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8501"
HEALTH = {
    "status": "configured",
    "provider": "openai_compatible",
    "configured": True,
    "message": "The primary AI provider was rate limited; the configured fallback handled the last request. Check primary provider quota.",
    "runtime_status": {
        "last_request_at": "2026-11-16T12:00:00+00:00",
        "last_status": "rate_limited",
        "last_provider": "openai_compatible",
        "fallback_active": True,
        "last_failure": "rate_limit",
    },
}


def main() -> None:
    evidence = {"local_url": BASE + "/admin", "checks": [], "page_errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        context.add_init_script("sessionStorage.setItem('pp_admin_session', 'local-browser-evidence-token')")

        def mocked_admin_api(route):
            path = route.request.url.split("?", 1)[0]
            if path.endswith("/api/admin/auth/status"):
                payload = {"locked": False, "remaining_seconds": 0}
            elif path.endswith("/api/admin/dashboard"):
                payload = {"status": "ok", "environment": "local", "recent_audits": [], "days_trend": []}
            elif path.endswith("/api/admin/users"):
                payload = {"users": []}
            elif path.endswith("/api/admin/waitlist"):
                payload = {"entries": []}
            elif path.endswith("/api/admin/revenue"):
                payload = {"total_revenue": 0, "transactions": []}
            elif path.endswith("/api/admin/ai-config"):
                payload = {"status": "ok", "config": {"provider": "openai_compatible", "model": "safe-test", "has_key": True}}
            elif path.endswith("/api/admin/ai-health"):
                payload = HEALTH
            elif path.endswith("/api/admin/feedback"):
                payload = {"entries": []}
            else:
                payload = {"status": "ok", "sessions": []}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        context.route("**/api/admin/**", mocked_admin_api)
        page = context.new_page()
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
        page.goto(BASE + "/admin", wait_until="networkidle")
        page.locator("#tab-ai-btn").click()
        alert = page.locator("#ai-provider-health-alert")
        alert.wait_for(state="visible")
        text = alert.inner_text()
        admin_js_loaded = any(
            "/assets/admin.js?v=15" in resource["name"]
            for resource in page.evaluate("performance.getEntriesByType('resource').map(item => ({name: item.name}))")
        )
        evidence["checks"] = [
            {"name": "admin_ai_health_alert_visible", "passed": alert.is_visible()},
            {"name": "admin_ai_health_reports_provider_rate_limit", "passed": "rate limited" in text.lower()},
            {"name": "admin_ai_health_reports_fallback_was_used", "passed": "fallback handled" in text.lower()},
            {"name": "admin_ai_health_contains_no_credentials", "passed": "secret" not in text.lower() and "api key" not in text.lower()},
            {"name": "admin_template_loads_cache_busted_script_v15", "passed": admin_js_loaded},
        ]
        evidence["rendered_status_text"] = text
        evidence["screenshot"] = "browser-id1-admin-health.png"
        page.screenshot(path=str(Path(__file__).resolve().parent / evidence["screenshot"]))
        browser.close()
    out = Path(__file__).resolve().parent / "browser-id1-admin-health.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not all(check["passed"] for check in evidence["checks"]) or evidence["page_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
