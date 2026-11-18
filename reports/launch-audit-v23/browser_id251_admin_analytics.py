from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

results = []
for round_no in (1, 2):
    with TemporaryDirectory(prefix=f"paperplane-id251-{round_no}-") as tmp:
        app, base, identities = helper.start_server(Path(tmp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.15)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                context.add_init_script(
                    "sessionStorage.setItem('pp_admin_session', "
                    + json.dumps(identities["admin"]) + ");"
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                fixture = {
                    "status": "ok", "environment": "development", "db_location": "local",
                    "total_users": 13, "free_users": 9, "pro_users": 2, "dev_users": 1,
                    "tier_breakdown": {"free": 9, "exam_pass": 1, "student_pro": 1, "pro": 1, "developer": 1},
                    "total_jobs": 987, "jobs_today": 7, "today_active": 3,
                    "new_signups_7d": 1, "total_waitlist": 0, "days_trend": [],
                    "waitlist_platforms": [], "top_operations": [], "recent_audits": [],
                }
                page.route("**/api/admin/dashboard", lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps(fixture)
                ))
                page.goto(base + "/admin", wait_until="networkidle")
                page.wait_for_function("document.querySelector('#legend-pro-val') === null && document.querySelector('#plan-breakdown-rows')?.children.length === 5", timeout=15000)
                rows = page.locator("#plan-breakdown-rows .legend-item")
                visible_rows = rows.all_text_contents()
                assert any("Exam Pass" in item and "1 (8%)" in item for item in visible_rows), visible_rows
                assert any("Developer Users" in item and "1 (8%)" in item for item in visible_rows), visible_rows
                assert any("Free Accounts" in item and "9 (69%)" in item for item in visible_rows), visible_rows
                assert page.locator("#m-total-jobs").inner_text() == "987"
                assert page.locator("#m-jobs-today").inner_text() == "7 jobs created today (UTC)"
                widths = page.locator("#meter-plan-segments > div").evaluate_all("els => els.map(e => parseFloat(e.style.width))")
                assert len(widths) == 5 and abs(sum(widths) - 100) < .01, widths
                assert not errors, errors
                results.append({"round": round_no, "plan_rows": visible_rows,
                                "meter_segment_widths": widths,
                                "total_jobs": page.locator("#m-total-jobs").inner_text(),
                                "jobs_today": page.locator("#m-jobs-today").inner_text(),
                                "page_errors": errors})
                page.screenshot(path=str(OUT / f"id251-admin-analytics-round{round_no}.png"))
                context.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

(OUT / "browser-id251-admin-analytics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
