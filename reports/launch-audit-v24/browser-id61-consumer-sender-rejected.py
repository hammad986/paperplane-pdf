"""Verify consumer-mailbox From addresses fail closed before provider dispatch."""
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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main() -> None:
    evidence: dict = {"provider_attempts": 0, "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id61-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "data"
        data_dir.mkdir()
        attempts_file = temp / "email-attempts.json"
        attempts_file.write_text('{"http":0,"smtp":0}', encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        runner = temp / "controlled_server.py"
        runner.write_text(
            '''import os, smtplib, urllib.request, uvicorn
import server
attempts = {"http": 0, "smtp": 0}
def save_attempts():
    from pathlib import Path
    Path(os.environ["PAPERPLANE_TEST_MAIL_SINK"]).write_text(__import__("json").dumps(attempts), encoding="utf-8")
def fake_urlopen(*args, **kwargs):
    attempts["http"] += 1
    save_attempts()
    raise AssertionError("unexpected outbound email request")
def fake_smtp(*args, **kwargs):
    attempts["smtp"] += 1
    save_attempts()
    raise AssertionError("unexpected SMTP connection")
urllib.request.urlopen = fake_urlopen
smtplib.SMTP = fake_smtp
smtplib.SMTP_SSL = fake_smtp
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
''',
            encoding="utf-8",
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith((
                "PAPERPLANE_", "SMTP_", "RESEND_", "CASHFREE_", "OPENAI_", "OPENROUTER_",
                "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_",
            ))
            and key not in {"TESTING", "SESSION_SECRET_KEY"}
        }
        env.update({
            "PAPERPLANE_SKIP_DOTENV": "1",
            "PAPERPLANE_ENV": "development",
            "PAPERPLANE_DATA_DIR": str(data_dir),
            "PAPERPLANE_PORT": str(port),
            "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
            "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
            "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
            "PAPERPLANE_SECURE_COOKIES": "false",
            "PAPERPLANE_TEST_MAIL_SINK": str(attempts_file),
            "RESEND_API_KEY": "controlled-not-a-real-key",
            "SMTP_ENABLED": "true",
            "SMTP_HOST": "smtp.invalid",
            "SMTP_USER": "owner@gmail.com",
            "SMTP_PASSWORD": "controlled-not-a-real-password",
            "SMTP_FROM_EMAIL": "owner@gmail.com",
            "PYTHONPATH": str(ROOT),
        })
        app = subprocess.Popen(
            [sys.executable, str(runner)], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                page.evaluate("window.openAuthModal('', 'register')")
                email = f"id61-{secrets.token_hex(4)}@example.test"
                page.locator("#auth-email").fill(email)
                page.locator("#auth-password").fill("SecurePass!23456")
                page.locator("#auth-confirm-password").fill("SecurePass!23456")
                with page.expect_response(lambda response: response.url.endswith("/api/auth/register")) as response_event:
                    page.locator("#auth-submit-btn").click()
                response = response_event.value
                payload = response.json()
                assert response.status == 503, {"status": response.status, "body": payload}
                assert payload.get("detail") == "Email delivery is unavailable. Please try again later or contact support."
                assert page.locator("#auth-otp-pane").is_hidden()
                assert page.locator("#auth-error").is_visible()
                assert not page.evaluate("localStorage.getItem('paperplane_token')")
                counts = json.loads(attempts_file.read_text(encoding="utf-8"))
                assert counts == {"http": 0, "smtp": 0}, counts
                evidence.update({
                    "http_status": response.status,
                    "guest_state_retained": True,
                    "otp_step_hidden": True,
                    "code_not_exposed": True,
                    "resend_and_smtp_attempts": counts,
                    "transport_env_used": "fake Resend key and fake SMTP credentials; no credentials or mail sent",
                })
                assert not evidence["page_errors"], evidence
                # The injected expected HTTP 503 is handled by the UI; do not count its resource line
                # as a browser application error.
                evidence["console_errors"] = [
                    error for error in evidence["console_errors"]
                    if "503 (Service Unavailable)" not in error
                ]
                assert not evidence["console_errors"], evidence
                evidence["result"] = "passed"
                page.screenshot(path=str(OUT / "browser-id61-consumer-sender-rejected.png"))
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)

    (OUT / "browser-id61-consumer-sender-rejected.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
