"""Exercise synthetic admin owner actions through the local Chromium UI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = r'''
import json, os, secrets
from pathlib import Path
import persistence, server, uvicorn
persistence.init_db()
email = "audit-ui-" + secrets.token_hex(5) + "@example.invalid"
password = secrets.token_urlsafe(24)
uid = persistence.create_user(email, password)
user_token = persistence.create_session(email, password)["token"]
persistence.increment_daily_usage("user:" + uid)
admin = persistence.create_admin_session(server.PRIMARY_ADMIN_EMAIL, "127.0.0.1")
Path(os.environ["ADMIN_IDENTITIES"]).write_text(json.dumps({"email": email, "uid": uid, "admin": admin, "user": user_token}))
server.ENVIRONMENT = "production"
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    results = []
    with tempfile.TemporaryDirectory(prefix="paperplane-admin-v15-") as tmp:
        directory = Path(tmp)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        identity_file = directory / "identities.json"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(48),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32), ADMIN_IDENTITIES=str(identity_file))
        proc = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError("Isolated admin server exited during startup")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated admin server did not start")
            identities = json.loads(identity_file.read_text())
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_init_script(f"sessionStorage.setItem('pp_admin_session', {json.dumps(identities['admin'])})")
                context.add_cookies([{"name": "paperplane_token", "value": identities["user"], "url": base}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/", wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                page.goto(base + "/admin", wait_until="domcontentloaded")
                row = page.locator("#users-tbody tr").filter(has_text=identities["email"])
                row.wait_for(state="visible", timeout=15000)
                row.get_by_role("combobox").select_option("student_pro")
                page.once("dialog", lambda dialog: dialog.accept())
                row.locator('[data-admin-user-action="set-plan"]').click()
                page.wait_for_function("""email => {
                  const row = [...document.querySelectorAll('#users-tbody tr')].find(x => x.innerText.includes(email));
                  return row && row.querySelector('.badge')?.innerText.trim() === 'STUDENT_PRO';
                }""", arg=identities["email"], timeout=15000)
                row = page.locator("#users-tbody tr").filter(has_text=identities["email"])
                page.once("dialog", lambda dialog: dialog.accept())
                row.locator('[data-admin-user-action="reset-usage"]').click()
                page.wait_for_timeout(250)
                assert page.locator("#users-tbody").inner_text().find(identities["email"]) >= 0
                assert not errors, errors
                with page.expect_response("**/api/admin/users") as response:
                    page.locator("#btn-refresh").click()
                users = response.value.json()["users"]
                user = next(item for item in users if item["email"] == identities["email"])
                assert user["last_active_at"] > 0, user
                results.append({"email": identities["email"], "plan": "student_pro",
                                "last_active_at_present": True, "admin_page_errors": errors,
                                "ui_actions": ["set-plan", "reset-usage"]})
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    out = Path(__file__).with_name("browser-admin.json")
    previous = json.loads(out.read_text()).get("rounds", []) if out.exists() else []
    combined = previous + results
    out.write_text(json.dumps({"rounds": combined}, indent=2))
    print(json.dumps({"rounds": len(combined), "result": combined}, indent=2))


if __name__ == "__main__":
    main()
