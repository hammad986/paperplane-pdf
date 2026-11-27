"""Exercise the UI-generated Developer API key in a real local Chrome browser."""
from __future__ import annotations

import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    with TemporaryDirectory(prefix="paperplane-v24-id94-") as tmp:
        temp = Path(tmp)
        data = temp / "data"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith((
            "PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
            "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_"))
            and k not in {"TESTING", "SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data), "PAPERPLANE_PORT": str(port),
            "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
            "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
            "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
            "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT),
            "PYTHONIOENCODING": "utf-8"})
        seed = ("import json; from persistence import init_db,create_user,create_session,set_user_tier; "
            "init_db(); email='id94@example.invalid'; password='Synthetic-Id94-Only!'; "
            "uid=create_user(email,password); set_user_tier(uid,'cyber_cafe'); "
            "print(json.dumps({'token':create_session(email,password)['token']}))")
        identity = json.loads(subprocess.run([sys.executable, "-c", seed], cwd=ROOT, env=env,
            capture_output=True, text=True, check=True, timeout=30).stdout)
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("local app did not start")
            base = f"http://127.0.0.1:{port}"
            evidence = {"page_errors": [], "console_errors": [], "production_endpoints_contacted": False}
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_cookies([{"name": "paperplane_token", "value": identity["token"],
                    "url": base, "httpOnly": True, "secure": False, "sameSite": "Lax"}])
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                    if message.type == "error" else None)
                response = page.goto(base + "/settings", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("window.state?.user?.tier === 'cyber_cafe'", timeout=15000)
                page.locator(".settings-tab-btn[data-tab='api']").click()
                form = page.locator("#settings-create-key-form")
                assert form.is_visible()
                page.locator("#settings-key-name").fill("ID94 browser generated key")
                with page.expect_response(lambda r: r.url.endswith("/api/developer/keys") and r.request.method == "POST") as generated:
                    page.locator("#settings-create-key-form button[type='submit']").click()
                generated_response = generated.value
                assert generated_response.status == 200, generated_response.status
                generated_body = generated_response.json()
                raw_key = generated_body["api_key"]
                assert raw_key.startswith("sk_live_")
                page.wait_for_function("document.querySelector('#settings-new-key-alert')?.hidden === false")
                bearer = page.request.get(base + "/api/v1/account/usage",
                    headers={"Authorization": "Bearer " + raw_key})
                x_api_key = page.request.get(base + "/api/v1/account/usage",
                    headers={"X-API-Key": raw_key})
                assert bearer.status == 200, bearer.status
                assert x_api_key.status == 200, x_api_key.status
                bearer_data = bearer.json()
                assert "daily_limit" in bearer_data and "calls_remaining" in bearer_data
                key_id = generated_body["id"]
                revoke = page.request.delete(base + f"/api/developer/keys/{key_id}",
                    headers={"Cookie": "paperplane_token=" + identity["token"]})
                assert revoke.status == 200, revoke.status
                revoked = page.request.get(base + "/api/v1/account/usage",
                    headers={"Authorization": "Bearer " + raw_key})
                assert revoked.status == 401, revoked.status
                evidence.update({"ui_generated_key": True, "key_value_recorded": False,
                    "key_prefix_only": raw_key[:12] + "…", "bearer_usage_status": bearer.status,
                    "x_api_key_usage_status": x_api_key.status, "usage_payload_valid": True,
                    "revoke_status": revoke.status, "revoked_key_status": revoked.status,
                    "result": "passed"})
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    (OUT / "browser-id94-fresh-api-key.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
