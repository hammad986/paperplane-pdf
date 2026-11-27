"""Verify all admin plan rows and distinct all-time/today job metrics in Chrome."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def seed_fixture(data_dir: Path, identities: dict) -> None:
    developer_email = identities["accounts"][0][0]
    seed = r"""
import sys, time
from pathlib import Path
import persistence
data_dir, developer_email = sys.argv[1], sys.argv[2]
users = persistence.admin_get_all_users()
developer = next(user for user in users if user["email"] == developer_email)
persistence.set_user_tier(developer["id"], "developer")
for tier, count in (("free", 8), ("pro", 2), ("exam_pass", 1)):
    for index in range(count):
        email = f"id251-{tier}-{index}@example.invalid"
        user_id = persistence.create_user(email, "test-password-251")
        persistence.set_user_tier(user_id, tier)
developer_id = next(user["id"] for user in persistence.admin_get_all_users() if user["email"] == developer_email)
job_ids = [persistence.create_job("compare", developer_id, 3600)[0] for _ in range(2)]
with persistence.connect() as connection:
    connection.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (time.time() - 2 * 86400, job_ids[0]))
    connection.commit()
"""
    seed_env = {**os.environ, "PAPERPLANE_DATA_DIR": str(data_dir), "PAPERPLANE_SKIP_DOTENV": "1"}
    subprocess.run([sys.executable, "-c", seed, str(data_dir), developer_email], cwd=ROOT, env=seed_env, check=True)


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id251-") as temp_name:
        temp = Path(temp_name)
        app, base, identities = helper.start_server(temp / "data")
        try:
            seed_fixture(temp / "data", identities)
            token = identities["admin"]
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("Local test server did not start")

            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_init_script(f"sessionStorage.setItem('pp_admin_session', {json.dumps(token)});")
                page = context.new_page()
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/admin", wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#dashboard-view')?.style.display !== 'none'", timeout=20000)
                page.wait_for_function("document.querySelector('#plan-breakdown-rows')?.children.length >= 6", timeout=20000)
                rows = page.locator("#plan-breakdown-rows tr").all_inner_texts()
                expected = {
                    "Free Accounts": "FreeAccounts969%",
                    "Exam Pass": "ExamPass18%",
                    "Pro Subscribers": "ProSubscribers215%",
                    "Student & Educator": "Student&Educator00%",
                    "Developer Users": "DeveloperUsers18%",
                    "All-In-One Pro & Developer": "All-In-OnePro&Developer00%",
                }
                compact_rows = ["".join(row.split()) for row in rows]
                for label, exact in expected.items():
                    assert exact in compact_rows, {"missing_or_wrong": exact, "rows": rows}
                assert "DeveloperUsers116%" not in compact_rows
                assert page.locator("#plan-breakdown-rows th[scope='row']").count() == 6
                assert page.locator(".tier-breakdown-table caption").inner_text() == "Account distribution by plan"
                assert page.locator("#m-total-jobs").inner_text().strip() == "2"
                assert page.locator("#m-jobs-today").inner_text().strip() == "1 jobs created today (UTC)"
                layouts = []
                for width in (320, 390, 820, 1366):
                    page.set_viewport_size({"width": width, "height": 900})
                    layout = page.evaluate("""() => {
                      const card = document.querySelector('#plan-breakdown-rows')?.closest('.chart-card');
                      const table = document.querySelector('.tier-breakdown-table');
                      const bounds = el => { const r = el.getBoundingClientRect(); return {left:r.left, right:r.right, width:r.width}; };
                      return {viewport:innerWidth, documentWidth:document.documentElement.scrollWidth,
                        card:bounds(card), table:bounds(table), tableScrollWidth:table.scrollWidth, tableClientWidth:table.clientWidth};
                    }""")
                    assert layout["documentWidth"] <= width, layout
                    assert layout["tableScrollWidth"] <= layout["tableClientWidth"] + 1, layout
                    assert layout["table"]["right"] <= layout["card"]["right"] + 1, layout
                    layouts.append(layout)
                evidence.update({"tier_rows": rows, "total_jobs": 2, "jobs_today": 1, "responsive_layouts": layouts})
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                page.screenshot(path=str(OUT / "browser-id251-admin-tier-breakdown.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

    evidence["result"] = "passed"
    (OUT / "browser-id251-admin-tier-breakdown.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
