"""Verify the admin Last Active column against a disposable recently active user."""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main() -> None:
    evidence = {"page_errors": [], "console_errors": [], "failed_requests": []}
    with TemporaryDirectory(prefix="paperplane-v24-id200-") as name:
        temp = Path(name)
        data = temp / "data"
        data.mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_", "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_"))
            and key not in {"TESTING", "SESSION_SECRET_KEY"}
        }
        env.update({
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data),
            "PAPERPLANE_PORT": str(port),
            "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
            "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
            "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
            "PAPERPLANE_SECURE_COOKIES": "false",
            "PYTHONPATH": str(ROOT),
        })
        os.environ.update(env)
        sys.path.insert(0, str(ROOT))
        import persistence
        import server

        email = f"audit-last-active-{secrets.token_hex(5)}@example.test"
        password = secrets.token_urlsafe(24)
        user_id = persistence.create_user(email, password)
        user_session = persistence.create_session(email, password)
        with TestClient(server.app) as api:
            user_response = api.get("/api/auth/me", headers={"Authorization": f"Bearer {user_session['token']}"})
            assert user_response.status_code == 200, user_response.text
            admin_session = persistence.create_admin_session(server.PRIMARY_ADMIN_EMAIL)
            api_rows = api.get("/api/admin/users", headers={"X-Admin-Session": admin_session}).json()["users"]
            api_row = next(row for row in api_rows if row["id"] == user_id)
            evidence["api_last_active_at"] = api_row.get("last_active_at")
            evidence["api_last_active_nonzero"] = bool(api_row.get("last_active_at"))

        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.add_init_script(f"sessionStorage.setItem('pp_admin_session', {json.dumps(admin_session)});")
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
                page.on("requestfailed", lambda request: evidence["failed_requests"].append({"url": request.url, "failure": request.failure}))
                response = page.goto(f"http://127.0.0.1:{port}/admin", wait_until="domcontentloaded")
                page.locator("#users-tbody").get_by_text(email).wait_for(timeout=30000)
                row = page.locator("#users-tbody tr").filter(has_text=email)
                cells = row.locator("td")
                evidence.update({
                    "http_status": response.status if response else None,
                    "email_visible": cells.nth(0).inner_text().strip() == email,
                    "last_active_cell": cells.nth(3).inner_text().strip(),
                    "status_cell": cells.nth(4).inner_text().strip(),
                })
                evidence["last_active_rendered"] = bool(evidence["last_active_cell"] and evidence["last_active_cell"] != "—")
                page.screenshot(path=str(OUT / "browser-id200-admin-last-active.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)

    evidence["passed"] = (
        evidence.get("http_status") == 200
        and evidence.get("api_last_active_nonzero")
        and evidence.get("email_visible")
        and evidence.get("last_active_rendered")
        and not evidence["page_errors"]
        and not evidence["console_errors"]
    )
    (OUT / "browser-id200-admin-last-active.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
