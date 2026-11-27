"""Verify admin session management and user access actions through the real local admin UI."""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-ids202-204-admin-ui.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

OWNER_ALIAS = "mdhammad29006@gmail.com"


def daily_usage(db_path: Path, email: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT count FROM user_usage WHERE subject=(SELECT 'user:' || id FROM users WHERE email=?) AND usage_date=date('now','localtime')",
            (email,),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def main():
    with TemporaryDirectory(prefix="paperplane-admin-ui-202-") as temp_name:
        data_dir = Path(temp_name) / "data"
        app, base, identities = helper.start_server(data_dir)
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            env = os.environ.copy()
            env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_DATA_DIR=str(data_dir))
            second_admin = subprocess.run(
                [sys.executable, "-c", f"from persistence import create_admin_session; print(create_admin_session({OWNER_ALIAS!r}))"],
                cwd=ROOT, env=env, check=True, capture_output=True, text=True,
            ).stdout.strip()
            accounts = identities["accounts"]
            set_plan = """
from persistence import get_user_by_email, set_user_tier
user = get_user_by_email(sys.argv[1])
set_user_tier(user['id'], 'cyber_cafe')
"""
            subprocess.run([sys.executable, "-c", "import sys\n" + set_plan, accounts[0][0]], cwd=ROOT, env=env, check=True, capture_output=True, text=True)
            seed_usage = """
from persistence import get_user_by_email, increment_daily_usage
import sys
for email in sys.argv[1:]:
    user = get_user_by_email(email)
    increment_daily_usage('user:' + user['id'])
"""
            subprocess.run([sys.executable, "-c", seed_usage, accounts[0][0], accounts[1][0]], cwd=ROOT, env=env, check=True, capture_output=True, text=True)

            evidence = {
                "user_accounts": [row[0] for row in accounts],
                "owner_alias": OWNER_ALIAS,
                "page_errors": [],
                "console_errors": [],
            }
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_init_script(f"sessionStorage.setItem('pp_admin_session',{json.dumps(identities['admin'])})")
                page = context.new_page()
                page.set_default_timeout(10000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                dialogs = []
                page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
                page.goto(base + "/admin", wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#dashboard-view')?.style.display !== 'none'")
                page.wait_for_function("document.querySelectorAll('#users-tbody tr [data-admin-user-action]').length >= 2")
                page.wait_for_function("document.querySelector('#plan-breakdown-rows')?.innerText.includes('All-In-One Pro & Developer')")
                plan_breakdown = page.locator("#plan-breakdown-rows").inner_text()
                evidence["canonical_paid_plan_name"] = "All-In-One Pro & Developer" in plan_breakdown
                evidence["legacy_cyber_cafe_label_absent"] = "Cyber Cafe" not in plan_breakdown
                cyber_cafe_user_row = page.locator("#users-tbody tr").filter(has_text=accounts[0][0])
                evidence["paid_user_badge_name"] = cyber_cafe_user_row.locator("td:nth-child(2) .badge").inner_text()
                evidence["paid_user_badge_uses_public_name"] = evidence["paid_user_badge_name"].upper() == "ALL-IN-ONE PRO & DEVELOPER"

                page.locator("#tab-sessions-btn").click()
                page.wait_for_function("document.querySelectorAll('#sessions-tbody tr').length >= 2")
                evidence["sessions_panel_visible"] = page.locator("#panel-sessions").is_visible()
                evidence["session_rows_before_revoke"] = page.locator("#sessions-tbody tr").count()
                evidence["session_alias_row_visible"] = page.locator("#sessions-tbody tr").filter(has_text=OWNER_ALIAS).count() == 1
                target_session_row = page.locator("#sessions-tbody tr").filter(has_text=OWNER_ALIAS)
                target_session_row.locator("button[data-session-id]").click()
                page.wait_for_function("document.querySelectorAll('#sessions-tbody tr').length === 1")
                evidence["session_rows_after_revoke"] = page.locator("#sessions-tbody tr").count()
                evidence["revoked_alias_session_status"] = page.request.get(base + "/api/admin/dashboard", headers={"X-Admin-Session": second_admin}).status
                evidence["current_admin_session_status"] = page.request.get(base + "/api/admin/dashboard", headers={"X-Admin-Session": identities["admin"]}).status

                page.locator("#tab-users-btn").click()
                target_email = accounts[1][0]
                target_row = page.locator("#users-tbody tr").filter(has_text=target_email)
                evidence["target_user_row_found"] = target_row.count() == 1
                evidence["target_usage_before"] = daily_usage(data_dir / "paperplane.sqlite3", target_email)
                evidence["comparison_usage_before"] = daily_usage(data_dir / "paperplane.sqlite3", accounts[0][0])
                target_row.locator("select").select_option("exam_pass")
                target_row.locator("button[data-admin-user-action='set-plan']").click()
                page.wait_for_function("email => [...document.querySelectorAll('#users-tbody tr')].some(row => row.innerText.includes(email) && row.querySelector('td:nth-child(2) .badge')?.innerText.trim() === 'EXAM PASS')", arg=target_email)
                evidence["plan_after_set"] = page.locator("#users-tbody tr").filter(has_text=target_email).inner_text()
                target_row = page.locator("#users-tbody tr").filter(has_text=target_email)
                target_row.locator("button[data-admin-user-action='reset-usage']").click()
                page.wait_for_function("email => [...document.querySelectorAll('#users-tbody tr')].some(row => row.innerText.includes(email))", arg=target_email)
                usage_deadline = time.monotonic() + 10
                while daily_usage(data_dir / "paperplane.sqlite3", target_email) != 0 and time.monotonic() < usage_deadline:
                    time.sleep(0.1)
                evidence["target_usage_after"] = daily_usage(data_dir / "paperplane.sqlite3", target_email)
                evidence["comparison_usage_after"] = daily_usage(data_dir / "paperplane.sqlite3", accounts[0][0])
                evidence["confirmation_dialogs"] = dialogs
                browser.close()

            evidence["result_202"] = "passed" if evidence["sessions_panel_visible"] and evidence["session_rows_before_revoke"] == 2 and evidence["session_alias_row_visible"] and evidence["session_rows_after_revoke"] == 1 and evidence["revoked_alias_session_status"] == 401 and evidence["current_admin_session_status"] == 200 else "failed"
            evidence["result_204"] = "passed" if evidence["target_user_row_found"] and "Exam Pass" in evidence["plan_after_set"] and evidence["target_usage_before"] == 1 and evidence["target_usage_after"] == 0 and evidence["comparison_usage_before"] == 1 and evidence["comparison_usage_after"] == 1 else "failed"
            evidence["overall"] = "passed" if evidence["result_202"] == evidence["result_204"] == "passed" and evidence["canonical_paid_plan_name"] and evidence["legacy_cyber_cafe_label_absent"] and evidence["paid_user_badge_uses_public_name"] and not evidence["page_errors"] and not evidence["console_errors"] else "failed"
            OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
            if evidence["overall"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
